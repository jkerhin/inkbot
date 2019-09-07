#!/usr/bin/python3
import utils
from inkbot import InkBot


def main():
    """Start up inkbot"""
    inkbot_dir = utils.get_inkbot_dir()
    config_pth = inkbot_dir / "inkbot.ini"
    config = utils.read_config(config_pth)
    config = utils.populate_config(config)

    inkbot = InkBot(
        user_agent=config["reddit"].get("user_agent"),
        user_name=config["reddit"].get("username"),
        user_pass=config["reddit"].get("password"),
        client_id=config["reddit"].get("client_id"),
        client_secret=config["reddit"].get("client_secret"),
        at_key=config["inkbot"].get("airtable_api_key"),
        at_base=config["airtable"].get("base"),
        at_table=config["airtable"].get("table"),
        subreddit=config["inkbot"].get("subreddit"),
        working_dir=inkbot_dir,
        debug=True,
    )
    inkbot.start()


if __name__ == "__main__":
    main()
