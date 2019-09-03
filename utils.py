import os
import sys
import configparser
from getpass import getpass
from pathlib import Path

TEMPLATE_PATH = "template.ini"
SECRETS_KEWORDS = ["pass", "secret", "key"]


def get_inkbot_dir():
    """Identify the directory that inkbot data will be written to"""
    platform = sys.platform
    if "win" in platform:
        # Windows, use %APPDATA%
        appdata = Path(os.environ["APPDATA"])
        base = appdata
    else:
        # Not Windows, assume unix-y
        usr_home = Path("~").expanduser()
        base = usr_home / ".local" / "share"
    return base / "inkbot"


def read_config(cfg_path=None):
    """Read in the inkbot config file

    If no path is specified, config will read from the default inkbot path.

    Parameters
    ==========
    cfg_path : string-y, default None
        The path to the inkbot configuration file

    Returns
    =======
    config : configparser.ConfigParser
        An object containing the parsed configuration

    """
    if not cfg_path:
        cfg_path = get_inkbot_dir() / "inkbot.ini"
    if not Path(cfg_path).is_file():
        # TODO: log this, maybe? For now, this will just return a valid object
        # with no keys or values
        pass
    config = configparser.ConfigParser()
    config.read(cfg_path)
    return config


def write_config(
    config, out_pth=(get_inkbot_dir() / "inkbot.ini"), secrets=True, overwrite=True
):
    """Write out the inkbot configuration file

    If no path is specified, config will written to the default inkbot path.

    Parameters
    ==========
    config : configparser.ConfigParser
        The configuration settings that will be written to disk
    cfg_path : pathlib.Path or string, default `get_inkbot_dir()` result
        The path that the config file will be saved to
    secrets : bool, default True
        If true, will write out the full config file. If set to false, none of the
        "password", "secret", or "key" values will be written
    overwrite : bool, default True
        Overwrite the existing file located at `out_pth`

    """
    out_pth = Path(out_pth)
    pth_exists = out_pth.is_file()
    if pth_exists and not overwrite:
        raise OSError(f"File already exists at {out_pth}.")
    if not secrets:
        # Remove all secrets before writing to disk
        for section in config.sections():
            for option in config.options(section):
                if any([(kw in option.lower()) for kw in SECRETS_KEWORDS]):
                    config.remove_option(section, option)
    with out_pth.open("w") as hdl:
        config.write(hdl)


def populate_config(config, template_pth=TEMPLATE_PATH):
    """Populate the inkbot config file, prompting user input for unpopulated options

    Given a ConfigParser instance specified by `config`, and a config template, iterate
    through all of the sections and options, making sure that `config` contains populated
    options for all options in the template

    TODO: Should I be handling keyboard exceptions here, or in the calling function?

    Parameters
    ==========
    config : configparser.ConfigParser
        A ConfigParser object that will can contain all, some, or none of the needed
        configuration values, and that will be populated by this function
    cfg_path : pathlib.Path or string, default TEMPLATE_PATH
        The path to a template config file, containing all of the sections and options
        needed to instantiate the inkbot

    Returns
    =======
    config : configparser.ConfigParser
        A ConfigParser object, with all of the sections and options defined in the
        template filled out.

    """
    template = configparser.ConfigParser()
    template.read(template_pth)
    for section in template.sections():
        if "test" in section:
            # Test sections not used in operational runs; don't prompt user
            continue
        if not config.has_section(section):
            config.add_section(section)
        for option in template.options(section):
            opt_val = config[section].get(option)
            if not opt_val:
                prompt_str = f"Please enter the {option} for {section}\n> "
                if any([(kw in option.lower()) for kw in SECRETS_KEWORDS]):
                    opt_val = getpass(prompt=prompt_str)
                else:
                    opt_val = input(prompt_str)
                config[section][option] = opt_val

    return config
