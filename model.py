"""! @file model.py
@brief Model classes for managing test execution and organization in a pytest-gui project.

This module provides the core data structures for representing and managing test cases,
methods, and test hierarchies in a GUI-based test runner. It includes classes for handling
test statuses, active states, and test discovery.
"""

from datetime import datetime
from events import EventSource
import sys


class ModelLoadError(Exception):
    """! Exception raised when there is an error loading the test model.
    
    @details This exception is used to wrap and propagate errors that occur during
             the loading or initialization of test models.
    """
    def __init__(self, trace):
        """! Constructor for ModelLoadError
        @param trace The error traceback or description
        """
        super(ModelLoadError, self).__init__()
        self.trace = trace


class TestMethod(EventSource):
    """! Represents a single test method within a test case.
    
    @details This class manages individual test methods, including their execution status,
             results, and active state. It inherits from EventSource to provide event
             notification capabilities.
    """
    
    ## Status code for passed tests
    STATUS_PASS = 100
    ## Status code for skipped tests
    STATUS_SKIP = 200
    ## Status code for expected failures
    STATUS_EXPECTED_FAIL = 300
    ## Status code for unexpected successes
    STATUS_UNEXPECTED_SUCCESS = 400
    ## Status code for failed tests
    STATUS_FAIL = 500
    ## Status code for tests with errors
    STATUS_ERROR = 600
    ## Tuple of status codes that indicate test failure
    FAILING_STATES = (STATUS_FAIL, STATUS_UNEXPECTED_SUCCESS, STATUS_ERROR)

    ## Dictionary mapping status codes to their string representations
    STATUS_LABELS = {
        STATUS_PASS: 'passed',
        STATUS_SKIP: 'skipped',
        STATUS_FAIL: 'failures',
        STATUS_EXPECTED_FAIL: 'expected failures',
        STATUS_UNEXPECTED_SUCCESS: 'unexpected successes',
        STATUS_ERROR: 'errors',
    }

    def __init__(self, name, testCase):
        """! Initialize a new test method
        @param name The name of the test method
        @param testCase The parent TestCase instance
        """
        self.name = name
        self.description = ''
        self._active = True
        self._result = None

        # Set the parent of the TestMethod
        self.parent = testCase
        self.parent[name] = self
        self.parent._update_active()

        # Announce that there is a new test method
        self.emit('new')

    def __repr__(self):
        """! String representation of the test method
        @return String representation including the full path
        """
        return u'TestMethod %s' % self.path

    @property
    def path(self):
        """! Get the full dotted path name of the test method
        @return String containing the full path
        """
        return u'%s.%s' % (self.parent.path, self.name)

    @property
    def active(self):
        """! Check if the test method is currently active
        @return Boolean indicating active state
        """
        return self._active

    def set_active(self, is_active, cascade=True):
        """! Set the active state of the test method
        @param is_active Boolean indicating desired active state
        @param cascade Whether to propagate the state change to parent
        """
        if self._active:
            if not is_active:
                self._active = False
                self.emit('inactive')
                if cascade:
                    self.parent._update_active()
        else:
            if is_active:
                self._active = True
                self.emit('active')
                if cascade:
                    self.parent._update_active()

    def toggle_active(self):
        """! Toggle the active state of the test method
        """
        self.set_active(not self.active)

    @property
    def status(self):
        """! Get the current status of the test method
        @return Status code or None if no result available
        """
        try:
            return self._result['status']
        except TypeError:
            return None

    @property
    def output(self):
        """! Get the test output
        @return Test output string or None if no result available
        """
        try:
            return self._result['output']
        except TypeError:
            return None

    @property
    def error(self):
        """! Get the test error information
        @return Error details or None if no error occurred
        """
        try:
            return self._result['error']
        except TypeError:
            return None

    @property
    def duration(self):
        """! Get the test execution duration
        @return Duration in seconds or None if not available
        """
        try:
            return self._result['duration']
        except TypeError:
            return None

    def set_result(self, status, output, error, duration):
        """! Set the test result information
        @param status The status code of the test execution
        @param output The output generated during test execution
        @param error Any error information if the test failed
        @param duration The time taken to execute the test
        """
        self._result = {
            'status': status,
            'output': output,
            'error': error,
            'duration': duration,
        }
        self.emit('status_update')


class TestCase(dict, EventSource):
    """! Represents a test case containing multiple test methods.
    
    @details A TestCase is a collection of related test methods, managing their
             organization and execution state. Inherits from both dict and EventSource.
    """

    def __init__(self, name, testApp):
        """! Initialize a new test case
        @param name The name of the test case
        @param testApp The parent test application instance
        """
        super(TestCase, self).__init__()
        self.name = name
        self._active = True

        # Set the parent of the TestCase
        self.parent = testApp
        self.parent[name] = self
        self.parent._update_active()

        # Announce that there is a new TestCase
        self.emit('new')

    def __repr__(self):
        """! String representation of the test case
        @return String representation including the full path
        """
        return u'TestCase %s' % self.path

    @property
    def path(self):
        """! Get the full dotted path name of the test case
        @return String containing the full path
        """
        return u'%s.%s' % (self.parent.path, self.name)

    @property
    def active(self):
        """! Check if the test case is currently active
        @return Boolean indicating active state
        """
        return self._active

    def set_active(self, is_active, cascade=True):
        """! Set the active state of the test case and optionally its children
        @param is_active Boolean indicating desired active state
        @param cascade Whether to propagate the state change to children and parent
        """
        if self._active:
            if not is_active:
                self._active = False
                self.emit('inactive')
                if cascade:
                    self.parent._update_active()
                for testMethod in self.values():
                    testMethod.set_active(False, cascade=False)
        else:
            if is_active:
                self._active = True
                self.emit('active')
                if cascade:
                    self.parent._update_active()
                for testMethod in self.values():
                    testMethod.set_active(True, cascade=False)

    def toggle_active(self):
        """! Toggle the active state of the test case
        """
        self.set_active(not self.active)

    def find_tests(self, active=True, status=None, labels=None):
        """! Find test methods matching specified criteria
        @param active Only include active tests if True
        @param status List of status codes to filter by
        @param labels List of test labels to filter by
        @return Tuple of (count, test_paths) where test_paths is either a list or single path
        """
        tests = []
        count = 0

        for testMethod_name, testMethod in self.items():
            include = True
            if active and not testMethod.active:
                include = False
            if status and testMethod.status not in status:
                include = False
            if labels and testMethod.path not in labels:
                include = False

            if include:
                count = count + 1
                tests.append(testMethod.path)

        if len(self) == count:
            return len(self), self.path

        return count, tests

    def _purge(self, timestamp):
        """! Remove test methods that aren't current as of the timestamp
        @param timestamp Datetime object to compare against
        """
        for testMethod_name, testMethod in self.items():
            if testMethod.timestamp != timestamp:
                self.pop(testMethod_name)

    def _update_active(self):
        """! Update this node's active status based on children's status
        """
        for testMethod_name, testMethod in self.items():
            if testMethod.active:
                self.set_active(True)
                return
        self.set_active(False)


class TestModule(dict, EventSource):
    """! Represents a module containing multiple test cases.
    
    @details A TestModule is a collection of related test cases, providing organizational
             structure and state management. Inherits from both dict and EventSource.
    """

    def __init__(self, name, parent):
        """! Initialize a new test module
        @param name The name of the module
        @param parent The parent module or project
        """
        super(TestModule, self).__init__()
        self.name = name
        self._active = True

        self.parent = parent
        self.parent[name] = self

        self.emit('new')

    def __repr__(self):
        """! String representation of the test module
        @return String representation including the full path
        """
        return u'TestModule %s' % self.path

    @property
    def path(self):
        """! Get the full dotted path name of the test module
        @return String containing the full path
        """
        if self.parent.path:
            return u'%s.%s' % (self.parent.path, self.name)
        return self.name

    @property
    def active(self):
        """! Check if the test module is currently active
        @return Boolean indicating active state
        """
        return self._active

    def set_active(self, is_active, cascade=True):
        """! Set the active state of the module and optionally its children
        @param is_active Boolean indicating desired active state
        @param cascade Whether to propagate the state change to children and parent
        """
        if self._active:
            if not is_active:
                self._active = False
                self.emit('inactive')
                if cascade:
                    self.parent._update_active()
                for testModule in self.values():
                    testModule.set_active(False, cascade=False)
        else:
            if is_active:
                self._active = True
                self.emit('active')
                if cascade:
                    self.parent._update_active()
                for testModule in self.values():
                    testModule.set_active(True, cascade=False)

    def toggle_active(self):
        """! Toggle the active state of the test module
        """
        self.set_active(not self.active)

    def find_tests(self, active=True, status=None, labels=None):
        """! Find test methods in this module matching specified criteria
        @param active Only include active tests if True
        @param status List of status codes to filter by
        @param labels List of test labels to filter by
        @return Tuple of (count, test_paths) where test_paths is either a list or single path
        """
        tests = []
        count = 0
        found_partial = False

        for testModule_name, testModule in self.items():
            include = True
            if active and not testModule.active:
                include = False

            if labels:
                if testModule.path in labels:
                    subcount, subtests = testModule.find_tests(True, status)
                else:
                    subcount, subtests = testModule.find_tests(active, status, labels)
            else:
                subcount, subtests = testModule.find_tests(active, status)

            if include:
                count = count + subcount
                if isinstance(subtests, list):
                    found_partial = True
                    tests.extend(subtests)
                else:
                    tests.append(subtests)

        if not found_partial:
            return count, self.path

        return count, tests

    def _purge(self, timestamp):
        """! Remove test modules that aren't current as of the timestamp
        @param timestamp Datetime object to compare against
        """
        for testModule_name, testModule in self.items():
            testModule._purge(timestamp)
            if len(testModule) == 0:
                self.pop(testModule_name)

    def _update_active(self):
        """! Update this node's active status based on children's status
        """
        for subModule_name, subModule in self.items():
            if subModule.active:
                self.set_active(True)
                return
        self.set_active(False)


class Project(dict, EventSource):
    """! Root class representing an entire test project.
    
    @details The Project class serves as the root container for all test modules,
             cases, and methods. It provides project-wide operations and state management.
             Inherits from both dict and EventSource.
    """

    def __init__(self):
        """! Initialize a new project
        """
        super(Project, self).__init__()
        self.errors = []

    def __repr__(self):
        """! String representation of the project
        @return String representation
        """
        return u'Project'

    @property
    def path(self):
        """! Get the project path (empty string for root)
        @return Empty string as projects are root nodes
        """
        return ''

    def find_tests(self, active=True, status=None, labels=None):
        """! Find all test methods in the project matching specified criteria
        @param active Only include active tests if True
        @param status List of status codes to filter by
        @param labels List of test labels to filter by
        @return Tuple of (count, test_paths) where test_paths is a list of matching tests
        """
        tests = []
        count = 0
        found_partial = False

        for testApp_name, testApp in self.items():
            include = True
            if active and not testApp.active:
                include = False

            if labels:
                if testApp.path in labels:
                    subcount, subtests = testApp.find_tests(True, status)
                else:
                    subcount, subtests = testApp.find_tests(active, status, labels)
            else:
                subcount, subtests = testApp.find_tests(active, status)

            if include:
                count = count + subcount
                if isinstance(subtests, list):
                    found_partial = True
                    tests.extend(subtests)
                else:
                    tests.append(subtests)

        if not found_partial:
            return count, []
        return count, tests

    def confirm_exists(self, test_label, timestamp=None):
        """! Ensure a test exists in the project hierarchy
        @param test_label The full dotted path of the test
        @param timestamp Optional timestamp for tracking test currency
        @return The created or existing TestMethod instance
        """
        parts = test_label.split('.')
        if len(parts) < 2:
            return

        parentModule = self
        for testModule_name in parts[:-2]:
            try:
                testModule = parentModule[testModule_name]
            except KeyError:
                testModule = TestModule(testModule_name, parentModule)
            parentModule = testModule

        try:
            testCase = parentModule[parts[-2]]
        except KeyError:
            testCase = TestCase(parts[-2], parentModule)

        try:
            testMethod = testCase[parts[-1]]
        except KeyError:
            testMethod = TestMethod(parts[-1], testCase)

        testMethod.timestamp = timestamp
        return testMethod

    def refresh(self, test_list, errors=None):
        """! Refresh the project's test hierarchy
        @param test_list List of test labels to include
        @param errors Optional list of errors encountered during refresh
        """
        timestamp = datetime.now()

        for test_label in test_list:
            self.confirm_exists(test_label, timestamp)

        for testModule_name, testModule in self.items():
            testModule._purge(timestamp)
            if len(testModule) == 0:
                self.pop(testModule_name)

        self.errors = errors if errors is not None else []

    def _update_active(self):
        """! Placeholder method for API consistency
        """
        pass


class UnittestProject(Project):
    """! Specialized Project class for unittest-based test projects.
    
    @details Extends the base Project class with specific functionality for
             unittest test discovery and execution.
    """

    def __init__(self):
        """! Initialize a new unittest project
        """
        super(UnittestProject, self).__init__()

    def discover_commandline(self, testdir='.'):
        """! Get the command line for test discovery
        @param testdir Directory to search for tests
        @return List of command line arguments for test discovery
        """
        return [sys.executable, 'discover.py', '--testdir', testdir]

    def execute_commandline(self, labels, testdir='.'):
        """! Get the command line for test execution
        @param labels List of test labels to execute
        @param testdir Directory containing tests
        @return List
        """
        args = [sys.executable, 'runner.py', '--testdir', testdir]
        return args + labels
