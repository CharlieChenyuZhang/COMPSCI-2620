class Actions:
    CREATE = "create"
    LOGIN = "login"
    LIST = "list"
    SEND = "send"
    LOAD_UNREAD = "load-unread"
    LOAD_PAST = "load-past"
    DELETE = "delete"
    DELETE_ACCOUNT = "delete_account"

class ResponseStatus:
    SUCCESS = "success"
    ERROR = "error"

class ResponseFields:
    STATUS = "status"
    MESSAGE = "message"
    UNREAD_COUNT = "unread_count"
    CHATS = "chats" 