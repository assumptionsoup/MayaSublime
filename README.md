# MayaSublime
### A Sublime Text 2/3 plugin

Send selected MEL/Python code snippets or whole files to Maya via commandPort

----------

### Installation

1. clone this repo into the `SublimeText -> Preference -> Browse Packages` directory:
`git clone git://github.com/assumptionsoup/MayaSublime.git`

2. Copy the scripts in the MayaScripts folder to a script folder in Maya's Path.

3. Add the following to your userScripts.py:

```python
import maya_sublime_interface
maya_sublime_interface.openPort(7001, sourceType="mel")
maya_sublime_interface.openPort(7002, sourceType="python")

```

4. If you change the port numbers in step 3, you will also need to edit
   the `MayaSublime.sublime-settings` file, setting the ports to match.

5. By default Sublime Text maps the `ctrl+enter` hotkey to the Add Line
   macro. You may wish to edit the Sublime Text's keymap file or Maya
   Sublime's keymap file to something else.

### Usage

To send a snippet, simply select some code in a mel or python script,
and hit `ctrl+return`, or right click and choose "Send To Maya". To send
the current file, do the same without a selection. This will source or
import/reload the file if it is on your Maya path.
