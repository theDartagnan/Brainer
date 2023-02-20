# Brainer: an multi-agent system to ask questions and answer them!

## In short

__Brainer__ is a python program that allows three kinds of agent to communicate each other through a RabbitMq 
Message Oriented Middleware.
These agents are :
- __asker__ : an interactive agent that allow the user to ask questions, and that prints out answers relative 
  to questions the user has asked when they arrived.
- __memory__ : an automatic agent that maintains a memory of questions and answers exchanged in a MongoDb database. 
  When a question comes from an asker, if it is already known with its answer, it will just send the answer back to 
  the asker. 
  If the question is unknown it will create it in its database. In this case, or if the question is known but not its 
  answer, it will __(i)__ save to the database, alongside the question, the personal queue identifier of the pending 
  asker, and __(ii)__ transmit the question to all the brainers. When an answer comes from a brainer, if the question 
  is unknown or if the answer is unknown from its database it will either save the question-answer couple, or update 
  the question to setup its answer and clear the potential pending aksers queues. If pending askers queues were present 
  in the database, it will send the answer to each of them.
- __brainer__ : an interactive agent that receives questions from memories and allow the user to answer to them. 
  The answer to a question is sent, alongside its relative question, to all connected memory, in order to broadcast 
  the knowledge.
  
## Prerequisite

For any usage prerequisites are:
- a Python environnement ≥ 3.9
- a reachable RabbitMq server ≥ 3.1

For the memory agent, the specific prerequisites are:
- a reachable MongoDb Database ≥ 4.2

## Setup

In order to use this program, python packages exposed in the requirements.txt file should be installed.

### Using a python virtual environment (preferred)

Using a python virtual env. allows managing different dependencies of different python projects separately. It avoids 
conflicts between different versions of a same package required in different projects, and allows getting easily rid of 
dependencies of a project when it is deleted.

To create a python virtual env, execute the following command within the project directory: 
```
python -m venv venv
```

Then activate the virtual env. with the following command (this step will also be required each time you want to launch
the program if the virtual env has not been already activated):
```
source venv/bin/activate
```

You can then install the requirements using the following pip command:
```
pip install -r requirements.txt
```

_[Optional]_ If you want to exit the virtual environment just execute the following command:
```
deactivate
```

### Installing the requirements without any python virtual environment

If you do not want to use a python virtual environment, you can simplify install the requirements with the following 
command:
```
pip install -r requirements.txt
```

## Configuration and launch

### Configuration file

Before starting an agent, you may want to configure the configuration.yml file present in the root of the project
directory. If this file has to be located somewhere else on the system, a parameter of the program will allow 
to indicate its path.

The configuration allow mentioning:
- __role__: the role of the agent. Either "asker", "memory" or "brainer". May be overridden with a program parameter
- __rabbitmq__: the RabbitMq server connection settings. If not present, the default server hostname will be 
  "localhost" with the default RabbitMq port (5672) and no credential. All sub-options are optional.
- __mongodb__: Only used by the memory agent, the MongoDb server connection settings. If not present, the default 
  server hostname will be "localhost" with the default MongoDb port (27017) and no credential. 
  The database used will be "brainers_db" and the collection will be "questions". All sub-options are optional.
  
Examples of different configuration files are given in the `docs/configurationSamples` directory.

### Launching Program

_Remember that if you use a python virtual environment you need to activate it before launching the program!_

The program signature is 
```
pyhton main.py [-h] [-c <configuration file>] [-r <application role>]
```

The optional arguments are :
- __-h__, __--help__: show a help message and exit 
- __-c \<configuration file\>__, __--config \<configuration file\>__: specify the configuration file location 
  (default is ./configuration.yml)
- __-r \<application role\>__, __--role \<application role\>__: specify the agent role. 
  Either 'asker', 'memory', or 'brainer'. 
  This parameter will override the role that may be indicated in the configuration file. 
  If the role is missing in the configuration file, and it is not given as a program parameter, an error will be raised.
