"""! @file runner.py
@brief Runner module for executing tests and handling their outputs in pytest-gui.

This module provides functionalities to execute test cases, manage their outputs,
and parse the results using subprocesses and threading.
"""

import json
import subprocess
import sys
from threading import Thread

try:
    from Queue import Queue, Empty
except ImportError:
    from queue import Queue, Empty  # python 3.x

from events import EventSource
from model import TestMethod
import pipes


def enqueue_output(out, queue):
    """! A utility method for consuming piped output from a subprocess.

    @param out The output stream to read from
    @param queue The queue to put the output lines into
    @details Reads content from `out` one line at a time, and puts it onto
             queue for consumption in a separate thread.
    """
    for line in iter(out.readline, b''):
        queue.put(line.strip().decode('utf-8'))
    out.close()


def parse_status_and_error(post):
    """! Parse the status and error information from the test result.

    @param post The test result dictionary
    @return A tuple containing the status code and error message
    """
    if post['status'] == 'OK':
        status = TestMethod.STATUS_PASS
        error = None
    elif post['status'] == 's':
        status = TestMethod.STATUS_SKIP
        error = 'Skipped: ' + post.get('error')
    elif post['status'] == 'F':
        status = TestMethod.STATUS_FAIL
        error = post.get('error')
    elif post['status'] == 'x':
        status = TestMethod.STATUS_EXPECTED_FAIL
        error = post.get('error')
    elif post['status'] == 'u':
        status = TestMethod.STATUS_UNEXPECTED_SUCCESS
        error = None
    elif post['status'] == 'E':
        status = TestMethod.STATUS_ERROR
        error = post.get('error')

    return status, error


class Runner(EventSource):
    """! A wrapper around the subprocess that executes tests.

    @details This class manages the execution of tests using subprocesses,
             capturing their outputs, and handling test result updates.
    """
    def __init__(self, project, count, labels, testdir):
        """! Initialize the Runner with the given project and test parameters.
        
        @param project The project instance containing the tests
        @param count The total number of tests to execute
        @param labels The specific test labels to run
        @param testdir The directory containing the tests
        """
        self.project = project

        self.proc = subprocess.Popen(
            self.project.execute_commandline(labels, testdir),
            stdin=None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            bufsize=1,
            close_fds='posix' in sys.builtin_module_names
        )

        # Piped stdout/stderr reads are blocking; therefore, we need to
        # do all our readline calls in a background thread, and use a
        # queue object to store lines that have been read.
        self.stdout = Queue()
        t = Thread(target=enqueue_output, args=(self.proc.stdout, self.stdout))
        t.daemon = True
        t.start()

        self.stderr = Queue()
        t = Thread(target=enqueue_output, args=(self.proc.stderr, self.stderr))
        t.daemon = True
        t.start()

        # The TestMethod object currently under execution.
        self.current_test = None

        # An accumulator of output from the tests. If buffer is None,
        # then the test suite isn't currently running - it's in suite
        # setup/teardown.
        self.buffer = None

        # An accumulator for error output from the tests.
        self.error_buffer = []

        # The timestamp when current_test started
        self.start_time = None

        # The total count of tests under execution
        self.total_count = count

        # The count of tests that have been executed.
        self.completed_count = 0

        # The count of specific test results.
        self.result_count = {}

    @property
    def is_running(self):
        """! Check if the runner is currently running.

        @return True if the runner is running, False otherwise
        """
        return self.proc.poll() is None

    @property
    def any_failed(self):
        """! Check if any tests have failed.

        @return The count of failed tests
        """
        return sum(self.result_count.get(state, 0) for state in TestMethod.FAILING_STATES)

    def terminate(self):
        """! Stop the executor.
        """
        self.proc.terminate()

    def poll(self):
        """! Poll the runner looking for new test output.

        @return True if the runner should continue polling, False otherwise
        """
        stopped = False
        finished = False

        # Read from stdout, building a buffer.
        lines = []
        try:
            while True:
                lines.append(self.stdout.get(block=False))
        except Empty:
            # queue.get() raises an exception when the queue is empty.
            # This means there is no more output to consume at this time.
            pass

        # Read from stderr, building a buffer.
        try:
            while True:
                self.error_buffer.append(self.stderr.get(block=False))
        except Empty:
            # queue.get() raises an exception when the queue is empty.
            # This means there is no more output to consume at this time.
            pass

        # Check to see if the subprocess is still running.
        # If it isn't, raise an error.
        if self.proc is None:
            stopped = True
        elif self.proc.poll() is not None:
            stopped = True

        # Process all the full lines that are available
        for line in lines:
            # Look for a separator.
            if line in (
                pipes.PipedTestResult.RESULT_SEPARATOR,
                pipes.PipedTestRunner.START_TEST_RESULTS,
                pipes.PipedTestRunner.END_TEST_RESULTS
            ):
                if self.buffer is None:
                    # Preamble is finished. Set up the line buffer.
                    self.buffer = []
                else:
                    # Start of new test result; record the last result
                    # Then, work out what content goes where.
                    pre = json.loads(self.buffer[0])
                    if len(self.buffer) == 2:
                        # No subtests are present, or only one subtest
                        post = json.loads(self.buffer[1])
                        status, error = parse_status_and_error(post)

                    else:
                        # We have subtests; capture the most important status (until we can capture all the statuses)
                        status = TestMethod.STATUS_PASS  # Assume pass until told otherwise
                        error = ''
                        for line_num in range(1, len(self.buffer)):
                            post = json.loads(self.buffer[line_num])
                            subtest_status, subtest_error = parse_status_and_error(post)
                            if subtest_status > status:
                                status = subtest_status
                            if subtest_error:
                                error += subtest_error + '\n\n'

                    # Increase the count of executed tests
                    self.completed_count = self.completed_count + 1

                    # Get the start and end times for the test
                    start_time = float(pre['start_time'])
                    end_time = float(post['end_time'])

                    self.current_test.description = post['description']

                    self.current_test.set_result(
                        status=status,
                        output=post.get('output'),
                        error=error,
                        duration=end_time - start_time,
                    )

                    # Work out how long the suite has left to run (approximately)
                    if self.start_time is None:
                        self.start_time = start_time
                    total_duration = end_time - self.start_time
                    time_per_test = total_duration / self.completed_count
                    remaining_time = (self.total_count - self.completed_count) * time_per_test
                    if remaining_time > 4800:
                        remaining = '%s hours' % int(remaining_time / 2400)
                    elif remaining_time > 2400:
                        remaining = '%s hour' % int(remaining_time / 2400)
                    elif remaining_time > 120:
                        remaining = '%s mins' % int(remaining_time / 60)
                    elif remaining_time > 60:
                        remaining = '%s min' % int(remaining_time / 60)
                    else:
                        remaining = '%ss' % int(remaining_time)

                    # Update test result counts
                    self.result_count.setdefault(status, 0)
                    self.result_count[status] = self.result_count[status] + 1

                    # Notify the display to update.
                    self.emit('test_end', test_path=self.current_test.path, result=status, remaining_time=remaining)

                    # Clear the decks for the next test.
                    self.current_test = None
                    self.buffer = []

                    if line == pipes.PipedTestRunner.END_TEST_RESULTS:
                        # End of test execution.
                        # Mark the runner as finished, and move back
                        # to a pre-test state in the results.
                        finished = True
                        self.buffer = None

            else:
                # Not a separator line, so it's actual content.
                if self.buffer is None:
                    # Suite isn't running yet - just display the output
                    # as a status update line.
                    self.emit('test_status_update', update=line)
                else:
                    # Suite is running - have we got an active test?
                    # Doctest (and some other tools) output invisible escape sequences.
                    # Strip these if they exist.
                    if line.startswith('\x1b'):
                        line = line[line.find('{'):]

                    # Store the cleaned buffer
                    self.buffer.append(line)

                    # If we don't have an currently active test, this line will
                    # contain the path for the test.
                    if self.current_test is None:
                        try:
                            # No active test; first line tells us which test is running.
                            pre = json.loads(line)
                        except ValueError:
                            self.emit('suit_end')
                            return True
                        self.current_test = self.project.confirm_exists(pre['path'])
                        self.emit('test_start', test_path=pre['path'])
        # If we're not finished, requeue the event.
        if finished:
            if self.error_buffer:
                self.emit('suite_end', error='\n'.join(self.error_buffer))
            else:
                self.emit('suite_end')
            return False

        elif stopped:
            # Suite has stopped producing output.
            if self.error_buffer:
                self.emit('suite_error', error='\n'.join(self.error_buffer))
            else:
                self.emit('suite_error', error='Test output ended unexpectedly')

            # Suite has finished; don't requeue
            return False

        else:
            # Still running - requeue event.
            return True


import argparse
import unittest


class PyTestExecutor(object):
    """! Executor class for running and streaming test results.

    @details This class is responsible for initiating test execution and
             streaming the results. It can handle specified test lists or
             discover tests from a directory.
    """
    
    def __init__(self):
        """! Initialize the PyTestExecutor.
        """
        # Allows the executor to run a specified list of tests
        self.specified_list = None

    def flatten_results(self, iterable):
        """! Flatten nested test results into a single list.

        @param iterable The iterable containing nested test results
        @return A generator yielding flattened test results
        """
        input = list(iterable)
        while input:
            item = input.pop(0)
            try:
                data = iter(item)
                input = list(data) + input
            except:
                yield item

    def run_only(self, specified_list):
        """! Set the list of tests to run exclusively.

        @param specified_list The list of test labels to run
        """
        self.specified_list = specified_list

    def stream_suite(self, suite):
        """! Stream the execution of the given test suite.

        @param suite The test suite to execute
        """
        print("Calling stream_suite: " + str(suite))
        pipes.PipedTestRunner().run(suite)

    def stream_results(self, testdir=None):
        """! Discover and stream test results from the specified directory.

        @param testdir The directory to discover tests from
        """
        if testdir is None:
            testdir = '.'

        loader = unittest.TestLoader()
        tests = loader.discover(testdir)
        flat_tests = list(self.flatten_results(tests))

        if not self.specified_list:
            suite = loader.discover(testdir)
            self.stream_suite(suite)
        else:
            suite = unittest.TestSuite()

            # Add individual test cases.
            for test in flat_tests:
                if test.id() in self.specified_list:
                    suite.addTest(test)

            # Add all tests in a file.
            for specified in self.specified_list:
                if specified.count('.') == 0:
                    for test in flat_tests:
                        module_name = test.id()[0:test.id().index('.')]
                        if specified == module_name:
                            suite.addTest(test)

            # Add all tests in a class within a file.
            for specified in self.specified_list:
                if specified.count('.') == 1:
                    for test in flat_tests:
                        module_name = test.id()[0:test.id().rindex('.')]
                        if specified == module_name:
                            suite.addTest(test)

            self.stream_suite(suite)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--testdir', dest='testdir', default='.', help='Directory to choose tests from')
    parser.add_argument('labels', nargs=argparse.REMAINDER, help='Test labels to run.')
    options = parser.parse_args()
    executor = PyTestExecutor()

    # options.labels = list()
    # options.labels.append('test_acquire.TestAcquire.test_print_1')

    if options.labels is not None:
        print('Labels: ', options.labels)

    if options.labels:
        executor.run_only(options.labels)
    executor.stream_results(options.testdir)
