'''Runs code sent from sublime_text.'''

import traceback
import __main__
import sys


def _exc_info_to_string():
    """Converts a sys.exc_info() - style tuple of values into a string
    and sets line numbers executed from selected text in sublime text to
    the correct value."""

    etype, value, tb = sys.exc_info()

    # Uncomment to dynamically query first msg line
    # msg = [traceback.format_exception(etype, value, tb)[0]]

    # Hardcode first line since I don't think it ever changes
    msg = ['Traceback (most recent call last):\n']

    # Hide up to exec and eval entry points
    while tb and _is_relevant_tb_level(tb):
        tb = tb.tb_next

    if tb:
        extracted_tb = traceback.extract_tb(tb)
        msg += traceback.format_list(extracted_tb)
    msg += traceback.format_exception_only(etype, value)

    return ''.join(msg)


def _is_relevant_tb_level(tb):
    return '__sublime_code_exec' in tb.tb_frame.f_globals


def execute_sublime_code(code, file_name='<sublime_code>', selected_lines=None):
    '''Executes or evaluates given code string and print result.

    file_name and selected_lines are used for exceptions and inspection
    to correctly represent the code sent from sublime text.'''

    # Define global variable that will later be used to hide this
    # executing function from exceptions
    global __sublime_code_exec
    __sublime_code_exec = 1

    eval_code = None
    exec_code = None
    try:
        # Try to eval code first, if this fails, then the code is most
        # likely not eval-able (has a statement in it)
        eval_code = compile(code, file_name, 'eval')
    except SyntaxError:
        # Clear exceptions, or it will muddle further exceptions in
        # unexpected ways
        sys.exc_clear()
        try:
            exec_code = compile(code, file_name, 'exec')
        except Exception:
            # There is an actual syntax error in the code provided.  Print it.
            print _exc_info_to_string()
            return

    try:
        if eval_code:
            result = eval(eval_code, __main__.__dict__, __main__.__dict__)
            if result:
                print repr(result)
        elif exec_code:
            exec(exec_code, __main__.__dict__, __main__.__dict__)
    except Exception:
        print _exc_info_to_string()
