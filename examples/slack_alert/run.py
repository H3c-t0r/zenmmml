#  Copyright (c) ZenML GmbH 2022. All Rights Reserved.
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at:
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express
#  or implied. See the License for the specific language governing
#  permissions and limitations under the License.
import click

POST = "post"
ASK = "ask"


@click.command()
@click.option(
    "--config",
    "-c",
    type=click.Choice([POST, ASK]),
    default=POST,
    help="Configure whether to run the post or ask pipeline.",
)
def main(config: str):
    """Run the Slack alerter example pipeline."""
    post = config == POST

    if post:
        from pipelines.post_pipeline import slack_post_pipeline

        slack_post_pipeline()
    else:
        from pipelines.ask_pipeline import slack_ask_pipeline

        slack_ask_pipeline()


if __name__ == "__main__":
    main()
