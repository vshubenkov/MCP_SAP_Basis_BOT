import config
from pyrfc import Connection, LogonError, CommunicationError

class SAPUserHandler:
    def __init__(self, host, sysnr, client, user, password):
        try:
            ##user_session.logger.info(f"Connecting to SAP system with host: {host}, system number: {sysnr}, client: {client}")
            self.conn = Connection(
                ashost=host,
                sysnr=sysnr,
                client=client,
                user=user,
                passwd=password
            )
            ##user_session.logger.info("Connection to SAP system established successfully.")
        except LogonError as e:
            #user_session.logger.error(f"Logon failed: {e}")
            raise Exception(f"Logon failed: {e}")
        except CommunicationError as e:
            #user_session.logger.error(f"Communication error: {e}")
            raise Exception(f"Communication error: {e}")
        except Exception as e:
            #user_session.logger.error(f"An error occurred while connecting: {e}")
            raise Exception(f"An error occurred: {e}")

    def get_user_list(self): #user_session):
        try:
            response = self.conn.call('BAPI_USER_GETLIST', WITH_USERNAME='X', MAX_ROWS=20000)
            return response.get('USERLIST', [])
        except Exception as e:
            #user_session.logger.error(f"An error occurred while fetching user list: {e}")
            raise Exception(f"An error occurred while fetching user list: {e}")

    def is_user_locked(self, username): #user_session):
        """
        Check if the user is locked by reading the USR02 table (UFLAG field)
        via RFC_READ_TABLE.
        UFLAG mapping:
          '128' -> "User is locked due to wrong logons."
          '0'   -> "User is not locked."
          else  -> "User is globally locked."
        Args:
            username (str): The SAP username whose lock state we want to check.
            #user_session (UserSession): Holds logger and other session details.

        Returns:
            str or None: Lock status message, or None if user is not locked.
        """
        try:
            #user_session.logger.info(f"Checking lock state for user: {username}")

            # Prepare the field and query condition for RFC_READ_TABLE
            fields_table = [{"FIELDNAME": "UFLAG"}]
            # We use a WHERE clause "BNAME = 'USERNAME'"
            # Adjust the syntax if your system needs eq or uppercase, etc.
            options_table = [{"TEXT": f"BNAME = '{username}'"}]

            # Call RFC_READ_TABLE to read USR02.UFLAG
            result = self.conn.call(
                'RFC_READ_TABLE',
                QUERY_TABLE='USR02',
                DELIMITER='|',
                FIELDS=fields_table,
                OPTIONS=options_table
            )

            #user_session.logger.info(f"Called RFC_READ_TABLE for user {username}, USR02.UFLAG")

            # The DATA field contains rows with WA key
            data_rows = result.get('DATA', [])
            if not data_rows:
                # No rows found -> no user or no record in USR02
                #user_session.logger.info(f"No record in USR02 for user {username}. Possibly user does not exist.")
                return None

            # For simplicity, we read the first row's WA
            raw_string = data_rows[0].get('WA', '').strip()
            #user_session.logger.info(f"UFLAG value for user {username}: '{raw_string}'")

            if raw_string == '128':
                return "User is locked due to wrong logons."
            elif raw_string == '0':
                #user_session.logger.info(f"User {username} is not locked.")
                return None  # None means not locked
            else:
                return "User is globally locked."

        except Exception as e:
            #user_session.logger.error(f"An error occurred while checking lock state for user {username}: {e}")
            raise Exception(f"An error occurred while checking lock state: {e}")

    def find_user(self, first_name, last_name): #user_session):
        try:
            #user_session.logger.info(f"Searching for user with first name: {first_name}, last name: {last_name}")
            user_list = self.get_user_list()
            matching_users = [
                user for user in user_list if user['FIRSTNAME'] == first_name and user['LASTNAME'] == last_name
            ]
            #user_session.logger.info(f"Found {len(matching_users)} matching users.")
            return matching_users
        except Exception as e:
            #user_session.logger.error(f"An error occurred while searching for user: {e}")
            raise Exception(f"An error occurred while searching for user: {e}")


def reset_password(sap_username, system_for_pass_reset):
    system_params = config.SAP_SYSTEM_DICT[system_for_pass_reset]
    try:
        ##user_session.logger.info(f"Initializing SAPUserHandler for system: {system_for_pass_reset}")
        sap_handler = SAPUserHandler(
            host=system_params['host'],
            sysnr=system_params['sysnr'],
            client=system_params['client'],
            user=system_params['user'],
            password=system_params['password']
        #    #user_session=#user_session
        )

        ##user_session.logger.info(f"Connected to SAP system: {system_for_pass_reset}")

        response = sap_handler.conn.call('BAPI_USER_CHANGE',
                             USERNAME=sap_username,
                             PASSWORDX={'BAPIPWD': 'X'},
                             GENERATE_PWD='X')
        # Check the RETURN structure
        return_messages = response.get('RETURN', [])
        for message in return_messages:
        #    #user_session.logger.info(f"{message['TYPE']} {message['ID']} {message['NUMBER']} {message['MESSAGE']}")
            if message['TYPE'] == 'E':
                # If an error occurred, return the error message
                return f"Error: {message['MESSAGE']}"

        generated_password = response.get('GENERATED_PASSWORD')
        if not generated_password:
        #    #user_session.logger.error("Password generation failed.")
            return "Error: Password generation failed."

        ##user_session.logger.info(f"Password for user {sap_username} has been successfully reset to new password.")

        # Optionally unlock the user
        #if sap_unlock_user:
        #    unlock_response = sap_handler.conn.call('BAPI_USER_UNLOCK', USERNAME=sap_username)
        #    if unlock_response['RETURN'][0]['TYPE'] not in ['S', 'W']:
        #        #user_session.logger.error(f"User unlock failed: {unlock_response['RETURN'][0]['MESSAGE']}")
        #        return False
        #   #user_session.logger.info(f"User {sap_username} has been successfully unlocked.")

        sap_handler.conn.call('BAPI_TRANSACTION_COMMIT')
        ##user_session.logger.info(f"Changes committed for user {sap_username}.")

        return True, generated_password

    except Exception as e:
        # Log the exception and return failure
        ##user_session.logger.error(f"An error occurred during password reset for user {sap_username}: {str(e)}")
        return False

    finally:
        # Close the connection in the finally block
        try:
            if 'sap_handler' in locals() and sap_handler.conn:
                sap_handler.conn.close()
        #        #user_session.logger.info("SAP connection closed.")
        except Exception as e:
            pass
        #    #user_session.logger.error(f"Error closing SAP connection: {str(e)}")