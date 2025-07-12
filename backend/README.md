# omni-poster
To create the VM i used venv module that comes with Python

# Activating the VM - Do this every time you start a new terminal session to work on project
    $ source .venv/bin/activate

# TIP
everytime you install a new package in the environment, activate the environment again. 
Ensures using CLI program installed by that package uses the one from VM, not globally. 

# Checking if VM active
which python

/home/user/code/awesome-project/.venv/bin/python - WORKING!


# Upgrade PIP - not using uv might transition tho
python -m pip install --upgrade pip

# Add gitignore
$echo "*" > .venv/.gitignore

# Install packages directly
if youre in a hurry and dont want to use a file to declare your package requirements, install directly

pip install "fastapi[standard]"

# TIP

Its a very good idea to put the packages and versions your program needs in a file (requirements.txt or pyproject.toml)


# Install from requirements.txt
if you have one you can use it to install packages
pip install -r requirements.txt

# deactivate VM
$ deactivate

#COnfigure editor

# start the live server

fastapi dev main.py
