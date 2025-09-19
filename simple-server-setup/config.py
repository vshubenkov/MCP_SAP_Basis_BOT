from dotenv import load_dotenv
import os
# Test
# Load environment variables from .env file
load_dotenv()

def load_sap_system_config():
    """ Load SAP system configurations dynamically from environment variables """
    return {
        'T42': {
            'host': os.environ.get("SAP_T42_HOST"),  # No default
            'sysnr': os.environ.get("SAP_T42_SYSNR"),  # No default
            'client': os.environ.get("SAP_T42_CLIENT"),  # No default
            'user': os.environ.get("SAP_T42_USER"),  # No default
            'password': os.environ.get("SAP_T42_PASSWORD"),  # No default
        },
        'T44': {
            'host': os.environ.get("SAP_T44_HOST"),  # No default
            'sysnr': os.environ.get("SAP_T44_SYSNR"),  # No default
            'client': os.environ.get("SAP_T44_CLIENT"),  # No default
            'user': os.environ.get("SAP_T44_USER"),  # No default
            'password': os.environ.get("SAP_T44_PASSWORD"),  # No default
        },
        'Z12': {
            'host': os.environ.get("SAP_Z12_HOST"),  # No default
            'sysnr': os.environ.get("SAP_Z12_SYSNR"),  # No default
            'client': os.environ.get("SAP_Z12_CLIENT"),  # No default
            'user': os.environ.get("SAP_Z12_USER"),  # No default
            'password': os.environ.get("SAP_Z12_PASSWORD"),  # No default
        },
        'Z14': {
            'host': os.environ.get("SAP_Z14_HOST"),  # No default
            'sysnr': os.environ.get("SAP_Z14_SYSNR"),  # No default
            'client': os.environ.get("SAP_Z14_CLIENT"),  # No default
            'user': os.environ.get("SAP_Z14_USER"),  # No default
            'password': os.environ.get("SAP_Z14_PASSWORD"),  # No default
        },
        'Z22': {
            'host': os.environ.get("SAP_Z22_HOST"),  # No default
            'sysnr': os.environ.get("SAP_Z22_SYSNR"),  # No default
            'client': os.environ.get("SAP_Z22_CLIENT"),  # No default
            'user': os.environ.get("SAP_Z22_USER"),  # No default
            'password': os.environ.get("SAP_Z22_PASSWORD"),  # No default
        }
    }
# Load the SAP System Dictionary dynamically
SAP_SYSTEM_DICT = load_sap_system_config()