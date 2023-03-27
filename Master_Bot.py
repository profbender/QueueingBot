import asyncio
import datetime
import discord
from discord.message import Message
from io import TextIOWrapper
import json
import sqlite3
import threading


class Master_Bot:

    def __init__(self):
        # Load config
        with open("config.json") as configFile:
            self.config: dict = json.load(configFile)

        # Load the valid users
        usernameFile: TextIOWrapper
        with open("validUserNames.txt") as usernameFile:
            self.validUsers: dict[str, str] = dict()
            for userInfo in usernameFile.readlines():
                userInfo: str = userInfo.strip().split("\t")
                self.validUsers[userInfo[0]] = " ".join(userInfo[1:])

        # Establish a connection to the users database
        self.connection = sqlite3.connect('users.db')

        # Create the Discord client
        intents = discord.Intents.default()
        intents.members = True
        eventLoop = asyncio.new_event_loop()
        self.client = discord.Client(intents=intents,
                                     loop=eventLoop)

        # Initialize a Queue for the users
        self.queue: asyncio.Queue = asyncio.Queue()

        # Initialize a dictionary mapping discordIDs to what the bot is expecting 
        # them to reply with
        self.waitingForReply: dict[int, str] = dict()

        # Register all events the Bot will listen for
        self.registerEvents()

        # Runs the client, initializing the event loop
        self.client.run(self.config.get('CLIENT_KEY'))

    def registeredUser(self, id: int) -> bool:
        """ Determines whether the given id is in the database of registered 
        users."""
        colbyUserName: str = self.connection.execute(f"""SELECT username FROM users 
            WHERE discordID = {id}""").fetchone()
        print(colbyUserName == None)
        if colbyUserName != None:
            return True
        else:
            return False

    def escapeString(self, string: str) -> str:
        """ Creates a copy of the given string where all double quotation marks 
            are replaced with single quotation marks."""
        return string.replace('\"', '\'')

    async def queueCommand(self, message: Message):
        """ Responds to the given message which has requested to enter the queue. 
        Registers the user hasn't registered their discordID to their Colby username yet. 
        Otherwise, asks for the student's reason."""
        if not self.registeredUser(message.author.id):
            await message.reply(f"<@{message.author.id}>: What is your Colby username?")
            with threading.Lock():
                self.waitingForReply[message.author.id] = "username"
        else:
            await self.getReason(message)

    async def enterQueue(self, message: Message):
        await self.queue.put(message.author.id)
        user: str = await self.getUser(message)
        print("user: " + user)
        self.connection.execute(f"""INSERT INTO queue (username, reason, timeEntered) VALUES
            (\"{user}\", \"{self.escapeString(message.content)}\", \"{str(datetime.datetime.now())}\")""")
        self.connection.commit()
        qsize: int = self.queue.qsize()
        await message.reply(f"<@{message.author.id}>: You're now in the queue. " + ("There are " + str(qsize - 1) + " people" if qsize != 2 else "There is 1 person") + " ahead of you.")

    async def registerUser(self, message: Message):
        username: str = self.escapeString(message.content).lower()
        command: str = f"""INSERT INTO users (discordID, username, name)
            VALUES ({message.author.id}, \"{username}\", \"{self.validUsers[username]}\")"""
        print("command: " + command)
        self.connection.execute(command)
        self.connection.commit()

    async def getReason(self, message: Message):
        await message.reply(f"<@{message.author.id}>: Please briefly describe your question.")
        with threading.Lock():
            self.waitingForReply[message.author.id] = "reason"

    async def getUser(self, message: Message) -> str:
        return self.connection.execute(f"""SELECT (username) FROM users 
            WHERE discordID = {message.author.id}""").fetchone()[0]

    def registerEvents(self):

        @self.client.event
        async def on_message(message: Message):
            """ This function is called whenever a message is read by this 
                bot"""

            with threading.Lock():
                print(message.content)
                print(type(message.author.id))

                # Ignore bot's own messages
                if message.author == self.client.user:
                    pass

                elif message.content.startswith("$enterQueue"):
                    await self.queueCommand(message)

                elif message.author.id in self.waitingForReply:
                    if self.waitingForReply.get(message.author.id) == "username":
                        if (message.content.lower() in self.validUsers):
                            await message.reply(f"<@{message.author.id}>: Great, I've paired your discord id to your Colby username.")
                            await self.registerUser(message)
                            await self.getReason(message)
                        else:
                            await message.reply(f"<@{message.author.id}>: username not found, check your spelling")
                    elif self.waitingForReply.get(message.author.id) == "reason":
                        with threading.Lock():
                            self.waitingForReply.__delitem__(message.author.id)
                        await self.enterQueue(message)


if __name__ == "__main__":
    Master_Bot()
