import sys
from argparse import ArgumentParser
from typing import Dict

import yaml

from agents.LauncherAgent import LauncherAgent


def configure_argument_parser() -> ArgumentParser:
    parser = ArgumentParser(description="Brainer agent: either an asker, a brainer or a memory.")
    parser.add_argument('-c', '--config', help="Configuration file location (default: ./configuration.yml)",
                        metavar='<configuration file>', type=str, default='./configuration.yml')
    parser.add_argument('-r', '--role', help="Role", metavar='<application role>', type=str,
                        choices=['asker', 'memory', 'brainer'], default=None)
    return parser


def read_configuration(configuration_file: str) -> Dict:
    with open(configuration_file) as f:
        return yaml.safe_load(f)


def create_asker(configuration: Dict) -> LauncherAgent:
    from agents.Asker import Asker
    return Asker(configuration)


def create_brainer(configuration: Dict) -> LauncherAgent:
    from agents.BrainerSimple import BrainerSimple
    return BrainerSimple(configuration)


def create_memory(configuration: Dict) -> LauncherAgent:
    from agents.Memory import Memory
    return Memory(configuration)


def main():
    try:
        # Create the argument parse and parse args
        arg_parser = configure_argument_parser()
        args = arg_parser.parse_args()
        # Read the configuration from the configuration file then validate it
        configuration = read_configuration(args.config)

        # According to the role, launch the proper app
        role = args.role if args.role is not None else configuration.get('role')
        if role is None:
            raise ValueError('Missing "role" mandatory field in configuration file and in parameters')
        if role == 'asker':
            app = create_asker(configuration)
        elif role == 'brainer':
            app = create_brainer(configuration)
        elif role == 'memory':
            app = create_memory(configuration)
        else:
            raise ValueError('Wrong role name: %s' % role)
        app.start()
        sys.exit(0)
    except Exception as e:
        print("Fatal exception: " + str(e))
        sys.exit(1)


if __name__ == '__main__':
    main()
