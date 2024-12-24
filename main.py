"""!
@file main.py
@brief Module for creating a project and running the main GUI loop.

This module serves as the entry point for the pytest-gui application.
It handles the initialization of the GUI window and project loading.
The module provides compatibility with both Python 2 (Tkinter) and Python 3 (tkinter).
"""

try:
    from Tkinter import *  #!< Python 2.x Tkinter import
except ImportError:
    from tkinter import *  #!< Python 3.x tkinter import

from view import MainWindow
from model import UnittestProject


def main_loop(Model=UnittestProject):
    """!
    @brief Run the main application loop.
    
    This function initializes and runs the main GUI application loop:
    1. Sets up the root Tk context
    2. Constructs the main window
    3. Loads the project model
    4. Starts the main event loop
    
    @param Model The project model class to use (defaults to UnittestProject)
    @return None
    
    @details
    The function creates a new Tkinter root window, initializes the MainWindow
    with this root context, loads the project using the specified Model class,
    and starts the Tkinter main event loop.
    
    Usage example:
    @code
    from main import main_loop
    main_loop()  # Run with default UnittestProject model
    @endcode
    """
    # Set up the root Tk context
    root = Tk()

    # Construct an empty window
    view = MainWindow(root)

    # Load the project model
    view.project = view.load_project(root, Model)

    # Run the main loop
    view.mainloop()


if __name__ == "__main__":
    main_loop()
