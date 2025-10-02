import config
from typing import TypedDict, List, Optional
from pyrfc import Connection, LogonError, CommunicationError, ABAPApplicationError, ABAPRuntimeError

class SapMessage(TypedDict, total=False):
    TYPE: str        # 'S', 'W', 'E', 'A', 'I'
    ID: str
    NUMBER: str
    MESSAGE: str
    LOG_NO: str
    LOG_MSG_NO: str
    MESSAGE_V1: str
    MESSAGE_V2: str
    MESSAGE_V3: str
    MESSAGE_V4: str

class ResetPasswordResult(TypedDict):
    success: bool
    password: Optional[str]
    messages: List[SapMessage]
    error: Optional[str]     # python-side exception message if any
    system: str
    username: str

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

def reset_password(
    sap_username: str,
    system_for_pass_reset: str,
    *,
    unlock_user: bool = False,
) -> ResetPasswordResult:
    """
    Reset an SAP user's password by calling BAPI_USER_CHANGE with GENERATE_PWD='X'.
    Returns a consistent structured result:
    {
        "success": bool,
        "password": str | None,
        "messages": [ {TYPE, ID, NUMBER, MESSAGE, ...}, ... ],
        "error": str | None,
        "system": <SID>,
        "username": <USER>,
    }
    """
    result: ResetPasswordResult = {
        "success": False,
        "password": None,
        "messages": [],
        "error": None,
        "system": system_for_pass_reset,
        "username": sap_username,
    }

    # --- Validate system config ---
    try:
        system_params = config.SAP_SYSTEM_DICT[system_for_pass_reset]
    except KeyError:
        result["error"] = f"Unknown system SID: {system_for_pass_reset}"
        return result

    required_keys = ("host", "sysnr", "client", "user", "password")
    missing = [k for k in required_keys if not system_params.get(k)]
    if missing:
        result["error"] = f"Missing SAP connection params: {', '.join(missing)}"
        return result

    sap_handler = None
    try:
        # --- Open connection ---
        sap_handler = SAPUserHandler(
            host=system_params["host"],
            sysnr=system_params["sysnr"],
            client=system_params["client"],
            user=system_params["user"],
            password=system_params["password"],
        )

        # --- Call password change with auto-generation ---
        resp = sap_handler.conn.call(
            "BAPI_USER_CHANGE",
            USERNAME=sap_username,
            PASSWORDX={"BAPIPWD": "X"},
            GENERATE_PWD="X",
        )

        # Collect messages
        messages: List[SapMessage] = list(resp.get("RETURN", []) or [])
        result["messages"] = messages

        # Any error message?
        has_error = any(m.get("TYPE") in ("E", "A") for m in messages)

        # Extract generated password
        generated_password = resp.get("GENERATED_PASSWORD")

        # Decide success / rollback vs. commit
        if has_error or not generated_password:
            # Roll back on any error or if password was not generated
            try:
                sap_handler.conn.call("BAPI_TRANSACTION_ROLLBACK")
            except Exception:
                pass  # best effort

            if has_error:
                # Summarize SAP-side error
                err_texts = [m.get("MESSAGE", "") for m in messages if m.get("TYPE") in ("E", "A")]
                result["error"] = "; ".join(t for t in err_texts if t) or "SAP error during password reset."
            else:
                result["error"] = "Password generation failed."
            return result

        # Optional unlock (best effort, do not fail the reset if unlock fails)
        if unlock_user:
            try:
                unlock_resp = sap_handler.conn.call("BAPI_USER_UNLOCK", USERNAME=sap_username)
                unlock_msgs = list(unlock_resp.get("RETURN", []) or [])
                result["messages"].extend(unlock_msgs)
                # Not treating unlock failure as hard error — add to messages only
            except Exception as e:
                # Record but don't fail the whole operation
                result["messages"].append({
                    "TYPE": "W",
                    "ID": "PY",
                    "NUMBER": "000",
                    "MESSAGE": f"Unlock step failed: {e}",
                })

        # Commit if all good
        sap_handler.conn.call("BAPI_TRANSACTION_COMMIT")

        # SUCCESS
        result["success"] = True
        result["password"] = generated_password
        return result

    except (CommunicationError, LogonError, ABAPApplicationError, ABAPRuntimeError) as e:
        # SAP-side exceptions
        result["error"] = f"SAP error: {e}"
        try:
            if sap_handler.conn:
                sap_handler.conn.call("BAPI_TRANSACTION_ROLLBACK")
        except Exception:
            pass
        return result

    except Exception as e:
        # Python-side exceptions
        result["error"] = f"Runtime error: {e}"
        try:
            if sap_handler.conn:
                sap_handler.conn.call("BAPI_TRANSACTION_ROLLBACK")
        except Exception:
            pass
        return result

    finally:
        try:
            if sap_handler.conn:
                sap_handler.conn.close()
        except Exception:
            pass