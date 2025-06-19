import asyncio
import logging

from pydoll.commands.page_commands import PageCommands
from pydoll.commands.target_commands import TargetCommands

from pydoll.connection.connection_handler import ConnectionHandler

# Navigate to a URL



class LinuxDoBrowser:
    async def home(self):
        connection = ConnectionHandler(9123)
        page = PageCommands.enable()  # Enable page events
        goto = PageCommands.navigate(url="https://linux.do")

        print(await connection.ping())

        ctx = TargetCommands.create_browser_context()
        tags = TargetCommands.get_targets()
        await connection.execute_command(ctx)
        print(await connection.execute_command(tags))
        new_target = TargetCommands.create_target(url="https://linux.do")
        await connection.execute_command(new_target)
        # await connection.execute_command(page)
        # await connection.execute_command(goto)



if __name__ == "__main__":
    asyncio.run(LinuxDoBrowser().home())