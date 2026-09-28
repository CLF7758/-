Prism — A Simple Reference Image Viewer
========================================

.. raw:: html

   <img align="left" width="100" height="100" src="https://raw.githubusercontent.com/rbreu/prism/main/prism/assets/logo.png">

`Prism <https://prism.org>`_ lets you quickly arrange your reference images and view them while you create. Its minimal interface is designed not to get in the way of your creative process.

|python-version| |github-ci-flake8| |github-ci-pytest| |codecov| |downloads-total| |downloads-latest|

.. image:: https://github.com/rbreu/prism/blob/main/images/screenshot.png

.. |python-version| image:: https://github.com/rbreu/prism/blob/main/images/python_version_badge.svg
   :target: https://www.python.org/

.. |github-ci-flake8| image:: https://github.com/rbreu/prism/actions/workflows/flake8.yml/badge.svg
   :target: https://github.com/rbreu/prism/actions/workflows/flake8.yml

.. |github-ci-pytest| image:: https://github.com/rbreu/prism/actions/workflows/pytest.yml/badge.svg
   :target: https://github.com/rbreu/prism/actions/workflows/pytest.yml

.. |codecov| image:: https://codecov.io/gh/rbreu/prism/branch/main/graph/badge.svg?token=QA8HR1VVAL
   :target: https://codecov.io/gh/rbreu/prism

.. |downloads-total| image:: https://img.shields.io/github/downloads/rbreu/prism/total.svg
   :target: https://github.com/rbreu/prism/releases

.. |downloads-latest| image:: https://img.shields.io/github/downloads/rbreu/prism/latest/total.svg
   :target: https://github.com/rbreu/prism/releases


Installation
------------

Stable Release
~~~~~~~~~~~~~~

Get the file for your operating system (Windows, Linux, macOS) from the `latest release <https://github.com/rbreu/prism/releases>`_. The different Linux versions are built on different versions of Ubuntu. The should work on other distros as well, but you might have to try which one works.

**Linux users** need to give the file executable rights before running it. Optional: If you want to have Prism appear in the app menu, save the desktop file from the `release section <https://github.com/rbreu/prism/releases>`_ in ``~/.local/share/applications``, save the `logo <https://raw.githubusercontent.com/rbreu/prism/main/prism/assets/logo.png>`_, and adjust the path names in the desktop file to match the location of your Prism installation.

**MacOS X users**, look at `detailed instructions <https://prism.org/macosx-run.html>`_ if you have problems running Prism.

Follow further releases via the `atom feed <https://github.com/rbreu/prism/releases.atom>`_.


Development Version
~~~~~~~~~~~~~~~~~~~

To get the current development version, you need to have a working Python 3 environment. Run the following command to install the development version::

  pip install git+https://github.com/rbreu/prism.git

Then run ``prism`` or ``prism filename.prism``.


Features
--------

* Move, scale, rotate, crop and flip images
* Mass-scale images to the same width, height or size
* Mass-arrange images vertically, horizontally or for optimal usage of space
* Add text notes
* Play videos (mp4, mov, avi, mkv, webm, wmv, flv, m4v, 3gp, ts) right on the canvas
* Enable always-on-top-mode and disable the title bar to let the Prism window unobtrusively float above your art program:

.. image:: https://github.com/rbreu/prism/blob/main/images/screenshot.png


Video support
~~~~~~~~~~~~~

Drag & drop video files onto the canvas just like images. Each video item
shows its first frame as a thumbnail when not playing.

* **Play/pause**: double-click the item, use the play button on the
  floating control bar, or the context menu.
* **Control bar**: hover the item to reveal a control bar with play/pause,
  a seek slider and the current/total time. It stays visible while the
  video is playing.
* **Context menu**: toggle *Loop Playback* and *Mute* per item.

Storage follows the same principle as images: videos up to
``Items/video_embed_threshold_mb`` (default 50 MB) are embedded into the
bee file's sqlar table, so the file stays portable. Larger videos are
referenced by absolute path and only their metadata is saved; if the
referenced file is missing when the bee file is opened, an error item is
shown instead.

The embed behavior can be controlled with the settings
``Items/video_embed_threshold_mb`` (size threshold in MB) and
``Items/video_embed_mode`` (``auto``: embed up to the threshold,
``embed``: always embed, ``reference``: never embed).

Playback uses QtMultimedia. On Windows, the Media Foundation backend is
used automatically when the ffmpeg backend's DLLs are unavailable.


Regarding the bee file format
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

All images are embedded into the bee file as PNG or JPG. The bee file format is a sqlite database inside which the images are stored in an sqlar table—meaning they can be extracted with the `sqlite command line program <https://www.sqlite.org/cli.html>`_::

  sqlite3 myfile.prism -Axv

Options for exporting from inside Prism are planned, but the above always works independently of Prism.


Troubleshooting
---------------

You can access the log output via *Help -> Show Debug Log*. In case Prism doesn't start at all, you can find the log file here:

Windows:

  C:\Documents and Settings\USERNAME\Application Data\Prism\Prism.log

Linux and MacOS:

  /home/USERNAME/.config/Prism/Prism.log


Notes for developers
--------------------

Prism is written in Python and PyQt6. For more info, see `CONTRIBUTING.rst <https://github.com/rbreu/prism/blob/main/CONTRIBUTING.rst>`_.
