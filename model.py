"""!
@file model.py
@brief Test project model implementation for the pytest-gui application.

This module provides the core data model classes for representing and managing
test projects, test cases, and test methods. It includes functionality for:
- Test discovery and organization
- Test status tracking
- Active/inactive state management
- Test result handling
"""

from datetime import datetime
from events import EventSource
import sys


class ModelLoadError(Exception):
    """!
    @brief Exception raised when there is an error loading the model.
    
    @param trace The error traceback information
    """
    def __init__(self, trace):
        super(ModelLoadError, self).__init__()
        self.trace = trace


class TestMethod(EventSource):
    """!
    @brief Represents a single test method within a test case.
    
    This class manages individual test methods, including their execution status,
    results, and active state. It emits events when its state changes.
    
    @note Inherits from EventSource to provide event emission capabilities
    """
    
    ## @name Test Status Constants
    ## @{
    STATUS_PASS = 100  ##< Test passed successfully
    STATUS_SKIP = 200  ##< Test was skipped
    STATUS_EXPECTED_FAIL = 300  ##< Test failed as expected
    STATUS_UNEXPECTED_SUCCESS = 400  ##< Test unexpectedly succeeded
    STATUS_FAIL = 500  ##< Test failed
    STATUS_ERROR = 600  ##< Test encountered an error
    ## @}
    
    ## List of states considered as failing
    FAILING_STATES = (STATUS_FAIL, STATUS_UNEXPECTED_SUCCESS, STATUS_ERROR)
    
    ## Status labels for human-readable output
    STATUS_LABELS = {
        STATUS_PASS: 'passed',
        STATUS_SKIP: 'skipped',
        STATUS_FAIL: 'failures',
        STATUS_EXPECTED_FAIL: 'expected failures',
        STATUS_UNEXPECTED_SUCCESS: 'unexpected successes',
        STATUS_ERROR: 'errors',
    }

    def __init__(self, name, testCase):
        """!
        @brief Initialize a new test method.
        
        @param name Name of the test method
        @param testCase Parent test case object
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
        """!
        @brief String representation of the test method.
        @return String containing the test method's full path
        """
        return u'TestMethod %s' % self.path

    @property
    def path(self):
        """!
        @brief The full dotted-path name that identifies this test method.
        @return String containing the full path to this test method
        """
        return u'%s.%s' % (self.parent.path, self.name)

    @property
    def active(self):
        """!
        @brief Check if this test method is currently active.
        @return bool indicating if the test is active
        """
        return self._active

    def set_active(self, is_active, cascade=True):
        """!
        @brief Set the active state of the test method.
        
        @param is_active Boolean indicating desired active state
        @param cascade If True, propagate state changes to parent
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
