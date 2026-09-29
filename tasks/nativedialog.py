from renpybuild.context import Context
from renpybuild.task import task


@task(kind="python", pythons="3", always=True)
def nativedialog(c: Context):
    """
    Installs the pure-python nativedialog module (native file and message
    dialogs without tkinter) into each platform's python library, so the
    pythonlib packaging step ships it in every py3 runtime.
    """

    c.copy("{{ root }}/nativedialog.py", "{{ install }}/lib/{{ pythonver }}/nativedialog.py")
