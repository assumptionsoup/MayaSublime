'''Runs code sent from sublime_text.'''

import __main__
import atexit
import errno
import maya.utils
import os
import socket
import maya.app.general.CommandPort as commandPort
import sys
import threading
import time
import traceback

import maya.cmds as cmds


_commandPorts = []
_pendingCommandPorts = []
_portThread = None
_portLock = threading.Lock()

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


def execute_sublime_code(code, filepath=None, selected_lines=None):
    '''Executes or evaluates given code string and print result.

    filename and selected_lines are used for exceptions and inspection
    to correctly represent the code sent from sublime text.'''

    # Define global variable that will later be used to hide this
    # executing function from exceptions
    global __sublime_code_exec
    __sublime_code_exec = 1

    eval_code = None
    exec_code = None

    if not filepath:
        filename = '<sublime_code>'
    else:
        filename = '<%s>' % filepath.split(os.path.sep)[-1]

    try:
        # Try to eval code first, if this fails, then the code is most
        # likely not eval-able (has a statement in it)
        eval_code = compile(code, filename, 'eval')
    except SyntaxError:
        # Clear exceptions, or it will muddle further exceptions in
        # unexpected ways
        sys.exc_clear()
        try:
            exec_code = compile(code, filename, 'exec')
        except Exception:
            # There is an actual syntax error in the code provided.  Print it.
            print _exc_info_to_string()
            return

    mainDict = __main__.__dict__
    if os.path.exists(filepath) and '__file__' in code:
        # Set __file__ in global space, in case the given code uses it
        exec('__file__ = %r' % filepath, mainDict, mainDict)
    try:
        if eval_code:
            result = eval(eval_code, mainDict, mainDict)
            print repr(result)
        elif exec_code:
            exec(exec_code, mainDict, mainDict)
    except Exception:
        print _exc_info_to_string()


class OpenCommandPort(threading.Thread):
    def run(self):
        global _commandPorts
        global _pendingCommandPorts
        global _portLock

        while _pendingCommandPorts:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            for port, kwargs in reversed(_pendingCommandPorts):
                try:
                    # Try to binding to the raw socket, instead of using
                    # command port to avoid errors with maya's
                    # cmds.commandPort (which will sometimes hang
                    # indefinitely if the port is in use)
                    sock.bind(('127.0.0.1', port))
                except socket.error:
                    # Socket is probably in use.
                    continue
                else:
                    sock.close()
                    time.sleep(0.5)

                # Lock is for _commandPorts and _pendingCommandPorts
                # modification.  I've also made sure opening commandPorts is
                # part of it, but I don't think that this is strictly
                # necessary.
                _portLock.acquire()
                try:
                    maya.utils.executeInMainThreadWithResult(
                        cmds.commandPort, name=":%d" % port, **kwargs)
                except RuntimeError:
                    pass
                else:
                    # Keep a record of opened ports to so we can close all
                    # open ports with closeAllPorts()
                    _commandPorts.append(port)
                    _pendingCommandPorts.remove([port, kwargs])

                    # Defer print statement so stdout isn't jumbled
                    cmds.evalDeferred(
                        "print 'Opened %s command port on %d'" % (
                            kwargs['sourceType'], port))
                finally:
                    _portLock.release()
            time.sleep(1)


def openPort(port, sourceType='python', **kwargs):
    '''
    Opens a commandPort for MayaSublime to communicate with.

    Will continue to try to open a commandPort in a separate thread if
    the commandPort cannot be created.  This is to help with creating a
    commandPort when there are multiple instances of mayas opened.  E.g
    if two instances of maya are open, and the first one is closed, the
    second one will then open a commandPort ensuring that communication
    between sublimeText and maya can continue.

    Given kwargs are passed to the cmds.commandPort command.
    '''
    global _portThread
    global _commandPorts

    kwargs['sourceType'] = sourceType
    if port in _commandPorts:
        closePort(port)

    _pendingCommandPorts.append([port, kwargs])
    if _portThread is None or not _portThread.is_alive():
        _portThread = OpenCommandPort()
        _portThread.start()


def closePort(port):
    '''
    Close a commandPort opened on the given port
    '''

    _portLock.acquire()
    cmds.commandPort(name=':%d' % port, close=True)
    if port in _commandPorts:
        _commandPorts.remove(port)
    _portLock.release()
    print 'Closed command port on %d' % port


def closeAllPorts():
    '''
    Close all commandPorts opened via the openPort() function.
    '''

    # closePort will modify _commandPorts, so we should avoid for loops.
    while _commandPorts:
        closePort(_commandPorts[0])


# Patch Maya to stop "[Errno 32] Broken pipe" errors from happening
# when the client (sublime) has closed the connection and maya tries to
# send a response (usually due to a timeout.
#
# As far as I know, THIS IS A GIANT UGLY HACK.  I need to use a
# jeweler's chisel, and I'm taking the biggest sledgehammer I can to
# this problem.  I do NOT know the proper way to solve this.  If you do,
# _please_ let me know.
def _patched_finish(self):
    if not self.wfile.closed:
        try:
            self.wfile.flush()
        except socket.error as e:
            # An final socket error may have occurred here, such as
            # the local error ECONNABORTED.
            pass
    try:
        self.wfile.close()
        self.rfile.close()
    except socket.error as e:
        if e.errno != errno.EPIPE:
            raise

_original_finish_ = commandPort.TcommandHandler.finish
commandPort.TcommandHandler.finish = _patched_finish

# Close command ports when maya exits.  Maya already handles this when
# it exits cleanly, but not when it crashes.  Depending on how severe
# the crash is, ports may still be left open even with this safety
# measure.
atexit.register(closeAllPorts)
