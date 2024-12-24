"""
@file pipes.py
@brief This file contains the implementation of custom unittest result and runner classes that output results in a machine-parseable format.
"""

from __future__ import absolute_import

import json
try:
    from StringIO import StringIO
except ImportError:
    from io import StringIO
import sys
import time
import traceback

import unittest

class PipedTestResult(unittest.result.TestResult):
    """
    @brief A test result class that can print test results in a machine-parseable format.
    """
    RESULT_SEPARATOR = '\x1f'  # ASCII US (Unit Separator)

    def __init__(self, stream, use_old_discovery=True):
        """
        @brief Constructor for PipedTestResult.

        @param stream The stream to which results will be written.
        @param use_old_discovery Whether to use old test discovery method.
        """
        super(PipedTestResult, self).__init__()
        self.stream = stream
        self.use_old_discovery = use_old_discovery
        self._first = True

        # Create a clean buffer for stdout content.
        self._stdout = StringIO()
        sys.stdout = self._stdout
        self._current_test = None

    def _trim_docstring(self, docstring):
        """
        @brief Trims the indentation from a docstring.

        @param docstring The docstring to trim.
        @return The trimmed docstring.
        """
        lines = docstring.expandtabs().splitlines()
        indent = sys.maxsize
        for line in lines[1:]:
            stripped = line.lstrip()
            if stripped:
                indent = min(indent, len(line) - len(stripped))
        trimmed = [lines[0].strip()]
        if indent < sys.maxsize:
            for line in lines[1:]:
                trimmed.append(line[indent:].rstrip())
        # Strip off trailing and leading blank lines:
        while trimmed and not trimmed[-1]:
            trimmed.pop()
        while trimmed and not trimmed[0]:
            trimmed.pop(0)
        # Return a single string:
        return '\n'.join(trimmed)

    def description(self, test):
        """
        @brief Provides a description for a test.

        @param test The test case.
        @return The description of the test.
        """
        try:
            # Wrapped _ErrorHolder objects have their own description
            return self._trim_docstring(test.description)
        except AttributeError:
            # Fall back to the docstring on the method itself.
            if test._testMethodDoc:
                return self._trim_docstring(test._testMethodDoc)
            else:
                return 'No description'

    def startTest(self, test):
        """
        @brief Called when a test is started.

        @param test The test case.
        """
        super(PipedTestResult, self).startTest(test)
        # We know we're starting a new test - record it.
        self._current_test = test
        self._stdout = StringIO()
        sys.stdout = self._stdout

        if self.use_old_discovery:
            parts = test.id().split('.')
            tests_index = parts.index('tests')
            path = '%s.%s.%s' % (parts[tests_index - 1], parts[-2], parts[-1])
        else:
            path = test.id()

        body = {
            'path': path,
            'start_time': time.time()
        }
        if self._first:
            self.stream.write(PipedTestRunner.START_TEST_RESULTS + '\n')
            self._first = False
        else:
            self.stream.write(self.RESULT_SEPARATOR + '\n')
        self.stream.write('%s\n' % json.dumps(body))
        self.stream.flush()

    def addSuccess(self, test):
        """
        @brief Called when a test has completed successfully.

        @param test The test case.
        """
        super(PipedTestResult, self).addSuccess(test)
        body = {
            'status': 'OK',
            'end_time': time.time(),
            'description': self.description(test),
            'output': self._stdout.getvalue(),
        }
        self.stream.write('%s\n' % json.dumps(body))
        self.stream.flush()
        self._current_test = None

    def addError(self, test, err):
        """
        @brief Called when a test raises an unexpected exception.

        @param test The test case.
        @param err The exception raised.
        """
        # If there's no current test, the error occurred during test
        # setup. Output a test start line so the protocol isn't confused.
        if self._current_test is None:
            self.startTest(test)

        super(PipedTestResult, self).addError(test, err)
        body = {
            'status': 'E',
            'end_time': time.time(),
            'description': self.description(test),
            'error': '\n'.join(traceback.format_exception(*err)),
            'output': self._stdout.getvalue(),
        }
        self.stream.write('%s\n' % json.dumps(body))
        self.stream.flush()
        self._current_test = None

    def addFailure(self, test, err):
        """
        @brief Called when a test fails.

        @param test The test case.
        @param err The exception raised.
        """
        super(PipedTestResult, self).addFailure(test, err)
        body = {
            'status': 'F',
            'end_time': time.time(),
            'description': self.description(test),
            'error': '\n'.join(traceback.format_exception(*err)),
            'output': self._stdout.getvalue(),
        }
        self.stream.write('%s\n' % json.dumps(body))
        self.stream.flush()
        self._current_test = None

    def addSubTest(self, test, subtest, err):
        """
        @brief Called when a subtest completes.

        @param test The test case.
        @param subtest The subtest case.
        @param err The exception raised.
        """
        super(PipedTestResult, self).addSubTest(test, subtest, err)
        if err is None:
            body = {
                'status': 'OK',
                'end_time': time.time(),
                'description': self.description(test),
                'output': self._stdout.getvalue(),
            }
            self.stream.write('%s\n' % json.dumps(body))
            self.stream.flush()
        elif issubclass(err[0], test.failureException):
            body = {
                'status': 'F',
                'end_time': time.time(),
                'description': self.description(test),
                'error': '\n'.join(traceback.format_exception(*err)),
                'output': self._stdout.getvalue(),
            }
            self.stream.write('%s\n' % json.dumps(body))
            self.stream.flush()
        else:
            body = {
                'status': 'E',
                'end_time': time.time(),
                'description': self.description(test),
                'error': '\n'.join(traceback.format_exception(*err)),
                'output': self._stdout.getvalue(),
            }
            self.stream.write('%s\n' % json.dumps(body))
            self.stream.flush()

    def addSkip(self, test, reason):
        """
        @brief Called when a test is skipped.

        @param test The test case.
        @param reason The reason for skipping.
        """
        super(PipedTestResult, self).addSkip(test, reason)
        body = {
            'status': 's',
            'end_time': time.time(),
            'description': self.description(test),
            'error': reason,
            'output': self._stdout.getvalue(),
        }
        self.stream.write('%s\n' % json.dumps(body))
        self.stream.flush()
        self._current_test = None

    def addExpectedFailure(self, test, err):
        """
        @brief Called when a test fails as expected.

        @param test The test case.
        @param err The exception raised.
        """
        super(PipedTestResult, self).addExpectedFailure(test, err)
        body = {
            'status': 'x',
            'end_time': time.time(),
            'description': self.description(test),
            'error': '\n'.join(traceback.format_exception(*err)),
            'output': self._stdout.getvalue(),
        }
        self.stream.write('%s\n' % json.dumps(body))
        self.stream.flush()
        self._current_test = None

    def addUnexpectedSuccess(self, test):
        """
        @brief Called when a test unexpectedly succeeds.

        @param test The test case.
        """
        super(PipedTestResult, self).addUnexpectedSuccess(test)
        body = {
            'status': 'u',
            'end_time': time.time(),
            'description': self.description(test),
            'output': self._stdout.getvalue(),
        }
        self.stream.write('%s\n' % json.dumps(body))
        self.stream.flush()
        self._current_test = None

class PipedTestRunner(unittest.TextTestRunner):
    """
    @brief A test runner class that displays results in machine-parseable format.
    """
    START_TEST_RESULTS = '\x02'  # ASCII STX (Start of Text)
    END_TEST_RESULTS = '\x03'    # ASCII ETX (End of Text)

    def __init__(self, stream=sys.stdout, use_old_discovery=False):
        """
        @brief Constructor for PipedTestRunner.

        @param stream The stream to which results will be written.
        @param use_old_discovery Whether to use old test discovery method.
        """
        self.stream = stream
        self.use_old_discovery = use_old_discovery

    def run(self, test):
        """
        @brief Run the given test case or test suite.

        @param test The test case or test suite to run.
        @return The test result.
        """
        # Remember stdout reference so it can be restored later
        old_stdout = sys.stdout

        # Create the result pipe, and run the tests with it.
        result = PipedTestResult(self.stream, self.use_old_discovery)
        test(result)

        # Report end of test run
        self.stream.write(self.END_TEST_RESULTS + '\n')
        self.stream.flush()

        # Restore the stdout reference
        sys.stdout = old_stdout
        return result
