from renpybuild.context import Context
from renpybuild.task import task, annotator


@annotator
def annotate(c: Context):
    c.include("{{ install }}/cubism/Core/include")
    if c.path("{{ tars }}/CubismSdkForNative-4-r.6.2.zip").exists(): c.env("CUBISM", "{{ install }}/cubism")


@task(platforms="all")
def build(c: Context):
    c.clean()

    c.var("cubism_zip", "CubismSdkForNative-4-r.6.2.zip")
    c.var("cubism_dir", "CubismSdkForNative-4-r.6.2")

    c.var("live2d", c.path("{{ root }}/live2d"))

    c.rmtree("{{ install }}/cubism")

    if c.path("{{ tars }}/{{ cubism_zip }}").exists():
        c.run("unzip -q {{ tars }}/{{ cubism_zip }}")
        c.run("mv {{cubism_dir}} {{ install }}/cubism")
    else:
        c.run("cp -a {{ root }}/live2d {{ install }}/cubism")
