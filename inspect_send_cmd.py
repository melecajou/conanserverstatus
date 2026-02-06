import inspect
from aiomcrcon import Client

print(inspect.signature(Client.send_cmd))
