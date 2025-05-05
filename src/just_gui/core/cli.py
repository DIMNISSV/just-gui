# src/just_gui/core/cli.py
import argparse
import asyncio
import logging
import sys
from PySide6.QtWidgets import QApplication, QMessageBox
import qasync
# from platformdirs import user_config_dir # Can import here, but used in AppCore

from .app import AppCore, APP_NAME, APP_AUTHOR  # <-- Import constants


# Basic logging setup (can be moved to a separate function)
def setup_logging():
    # Configure the root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.WARNING)  # Default for other libraries - WARNING

    # Configure our application logger
    app_logger = logging.getLogger('just_gui')
    # Level will be set later from config, for now set DEBUG to see AppCore.__init__ logs
    app_logger.setLevel(logging.DEBUG)
    app_logger.propagate = False  # Do not propagate messages to root

    # Create a handler for console output
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)

    # Add the handler to our logger
    if not app_logger.handlers:
        app_logger.addHandler(handler)

    # Can add a FileHandler if needed
    # file_handler = logging.FileHandler("app.log")
    # file_handler.setFormatter(formatter)
    # app_logger.addHandler(file_handler)


setup_logging()  # Call logging setup when the module is loaded
logger = logging.getLogger(__name__)  # Get logger for cli (__name__ will be 'just_gui.core.cli')


def main():
    """Main function to run the application."""
    parser = argparse.ArgumentParser(description="Run the just-gui application.")
    parser.add_argument(
        "--profile",
        type=str,
        required=True,
        help="Path to the application profile file (*.toml)",
    )
    args = parser.parse_args()

    logger.info(f"Starting just-gui with profile: {args.profile}")

    # Creating QApplication BEFORE the qasync event loop
    # Use try...except for QApplication as it might already exist
    try:
        qapp = QApplication.instance()
        if qapp is None:
            logger.debug("Creating a new QApplication instance.")
            # Pass sys.argv to QApplication
            qapp = QApplication(sys.argv)
        else:
            logger.debug("Using an existing QApplication instance.")
    except Exception as e:
        print(f"Critical error creating QApplication: {e}", file=sys.stderr)
        sys.exit(1)

    # Setup qasync
    loop = qasync.QEventLoop(qapp)
    asyncio.set_event_loop(loop)
    app_core = None  # Initialize the variable

    try:
        # --- Step 1: Create AppCore instance (synchronous) ---
        logger.debug("Creating AppCore instance...")
        app_core = AppCore(profile_path=args.profile)
        logger.debug("AppCore instance created.")

        # --- Step 2: Asynchronous initialization (plugin loading, view restoration) ---
        logger.debug("Starting asynchronous AppCore initialization...")
        # Use loop.run_until_complete to execute async initialize()
        # before starting the main loop
        loop.run_until_complete(app_core.initialize())
        logger.debug("Asynchronous AppCore initialization finished.")

        # --- Step 3: Show the window ---
        logger.debug("Displaying the main window...")
        app_core.show()
        logger.debug("Main window displayed.")

        # --- Step 4: Start the main event loop ---
        with loop:
            logger.info("Starting the main event loop...")
            loop.run_forever()  # Start the infinite Qt event loop

        logger.info("Main event loop finished.")
        # Code after loop.run_forever() will execute after the application closes (when the window is closed)

    except Exception as e:
        logger.critical(f"Unhandled top-level exception: {e}", exc_info=True)
        # Show critical error to user if GUI is still running
        try:
            # QMainWindow might be unavailable, use None as parent
            QMessageBox.critical(
                None,  # No parent window as app_core might not have been created/is damaged
                "Critical Error",
                f"An unexpected error occurred:\n{e}\n\nThe application will close."
            )
            # Ensure the Qt application quits after showing the error
            if qapp:
                qapp.quit()  # Attempting to quit Qt application
        except Exception as msg_e:
            # If even QMessageBox didn't work, print to stderr
            print(f"Application critical error: {e}\nError showing error message: {msg_e}", file=sys.stderr)
        sys.exit(1)  # Exit with error code
    finally:
        # Clean up asyncio loop (recommended)
        # Check loop state before closing
        if loop.is_running():
            logger.debug("Stopping asyncio event loop before closing...")
            loop.stop()  # Stop, if run_forever somehow finished otherwise
        logger.debug("Closing asyncio event loop...")
        loop.close()
        logger.info("Asyncio event loop closed.")
        # sys.exit(0) # Normal exit if no errors occurred (already happens via app.exec())


if __name__ == "__main__":
    main()
