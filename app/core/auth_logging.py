"""O código de autorização e o state do callback não entram no access log."""
import logging


class AuthQueryFilter(logging.Filter):
    def filter(self, record):
        args = record.args
        if isinstance(args,tuple) and len(args)==5 and isinstance(args[2],str):
            if args[2].split("?",1)[0].rstrip("/")=="/auth/google/callback":
                record.args = (*args[:2], "/auth/google/callback", *args[3:])
        return True


def install_auth_log_filter():
    logger = logging.getLogger("uvicorn.access")
    if not any(isinstance(f,AuthQueryFilter) for f in logger.filters):
        logger.addFilter(AuthQueryFilter())
