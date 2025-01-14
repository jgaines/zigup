# zigup

Simplistic tool to inject then dev-latest version of zig and zls into the mise
installs directory structure. It uses JSON endpoints in both projects to
determine the latest daily build and if it's newer than whats currently
installed, it installs it into the mise/installs/zig folder and sets up a
dev-latest symlink to it.

Once the dev-latest has been installed, you can `mise use zig@dev-latest` to use
it and the corresponding zls (Zig Language Server).

# Caveats

I whipped this up in a day just to solve the problem of mise being unable to
install the daily builds of zig and zls.  I did this because I wanted to work
through [ziglings](https://ziglings.org), which assumes you're using a recent
daily build.

I have only tested this on a linux machine.  The code to handle installs on a
Mac is partially done though untested as I don't have access to a Mac at the
moment. The code to handle Windows is not written at all, though there are some
commented out bits in the right places for it.

# Usage

There are no command line options to this at the moment.  It also assumes you've
already installed at least one version of zig using mise.  So if you haven't
already, you must at a minimum run (`install` or `use` both work):

```bash
mise install zig
```

I haven't bothered to publish this on pypi because I'm hoping it won't be needed
for too long and because it's not complete or very well polished. To use the
script, you can clone the repo and use pipx or uv install it from the repo, or
simply download the src/zigup.py script by itself and use `uv run` to execute it
(it has inline dependencies which uv run can make use of).

## Clone and Install

```bash
git clone https://github.com/jgaines/zigup.git
cd zigup
uv tool install .
```

You can substitute `pipx` for `uv tool` above if you prefer that.

## Download Script and Run with uv

Now that uv has support for in-script dependencies, you can simply download a
script with inline dependencies and run it directly.  uv will take care of
creating a temporary virtual environment, install dependencies into it and run
the script in the context of that venv.

```bash
wget https://raw.githubusercontent.com/jgaines/zigup/master/src/zigup.py
uv run zigup.py
```
