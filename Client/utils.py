import sys
from pathlib import Path

def get_server_config():
    try:
        from config import server_host, server_port
    except ImportError:
        sys.path.append(str(Path(__file__).parent.parent))
        from config import server_host, server_port
    return server_host, server_port
