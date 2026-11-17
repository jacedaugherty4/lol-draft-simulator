import boto3
from dotenv import load_dotenv

load_dotenv() #loads AWS profile from .env

REGION="us-east-2"
PARAM_NAME="/lds/riot-api-key"
BUCKET="lds-data-jacedaugherty4-640110192824-us-east-2-an"

def get_riot_api_key() -> str:
    """Fetch API key from AWS parameter storage."""
    ssm = boto3.client("ssm", region_name =REGION)
    response = ssm.get_parameter(Name = PARAM_NAME, WithDecryption=True)
    return response["Parameter"]["Value"]