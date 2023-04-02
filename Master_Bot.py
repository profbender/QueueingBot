import asyncio
import datetime
import discord
from discord.message import Message
from io import TextIOWrapper
import json
import sqlite3
import threading


class Master_Bot:

    class QueueData:
        """ Container class for people in the queue"""

        def __init__(self, name: str, reason: str, entry: int, discordID: int):
            self.name: str = name
            self.discordID: int = discordID
            self.reason: str = reason
            self.next: Master_Bot.QueueData = None
            self.entry: int = entry
            self.startTime: datetime.datetime = None

    class Queue:
        """ Queue manager with thread locking"""

        def __init__(self):
            self.start: Master_Bot.QueueData = None
            self.end: Master_Bot.QueueData = None
            self.size: int = 0

        def offer(self, name: str, reason: str, entry: int, discordID: int) -> int:
            with threading.Lock():
                if self.size == 0:
                    self.start = Master_Bot.QueueData(
                        name, reason, entry, discordID)
                    self.end = self.start
                else:
                    self.end.next = Master_Bot.QueueData(
                        name, reason, entry, discordID)
                    self.end = self.end.next
                self.size += 1
                return self.size - 1

        def poll(self) -> 'Master_Bot.QueueData':
            with threading.Lock():
                if self.size == 0:
                    return None
                else:
                    toReturn: Master_Bot.QueueData = self.start
                    self.start = self.start.next
                    if self.start == None:
                        self.end = None
                    self.size -= 1
                    return toReturn

        def __contains__(self, id: int) -> bool:
            with threading.Lock():
                cur: Master_Bot.QueueData = self.start
                while cur != None:
                    if cur.discordID == id:
                        return True
                    cur = cur.next
                return False

        def findPosition(self, id: int) -> int:
            curIndex: int = 0
            with threading.Lock():
                cur: Master_Bot.QueueData = self.start
                while (cur != None):
                    if (cur.discordID == id):
                        return curIndex
                    curIndex += 1
                    cur = cur.next
                return -1

        def __repr__(self):
            out: str = ""
            cur = self.start
            while(cur != None):
                out += cur.name + ", "
                cur = cur.next
            return out

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

        # Get a reference to myID
        self.benderID: int = self.config.get("BENDER_ID")

        # Initialize a Queue for the users
        self.queue: Master_Bot.Queue = Master_Bot.Queue()

        # Initialize a reference to whomever is currently getting served
        self.current: Master_Bot.QueueData = None

        # Initialize a dictionary mapping discordIDs to what the bot is expecting
        # them to reply with
        self.waitingForReply: dict[int, str] = dict()

        # Register all events the Bot will listen for
        self.registerEvents()

        # Runs the client, initializing the event loop
        self.client.run(self.config.get('CLIENT_KEY'))

    def escapeString(self, string: str) -> str:
        """ Creates a copy of the given string where all double quotation marks 
            are replaced with single quotation marks."""
        return string.replace('\"', '\'')

    async def queueCommand(self, message: Message):
        """ Responds to the given message which has requested to enter the queue. 
            Registers the user hasn't registered their discordID to their Colby 
            username yet. Otherwise, asks for the student's reason."""

        if not self.isRegistered(message.author.id):
            await message.reply(f"<@{message.author.id}>: What is your Colby username?")
            with threading.Lock():
                self.waitingForReply[message.author.id] = "username"
        else:
            if message.author.id in self.queue:
                await message.reply(f"<@{message.author.id}>: You're already in the queue")
                return
            await self.getReason(message)

    async def registerUser(self, discordID: int, username: str):
        """ Registers the user in the database."""
        with threading.Lock():
            self.connection.execute(f"""INSERT INTO users (discordID, username, name)
                VALUES ({discordID}, \"{username}\", \"{self.validUsers[username]}\")""")
            self.connection.commit()

    async def enterQueue(self, message: Message):
        """ Uses the info the given message to attempt to put the associated user 
            into the queue. If the user already is in the queue, notifies the user 
            and ignores request."""

        name: str = self.getName(message.author.id)
        with threading.Lock():
            username: str = self.getColbyUsername(message.author.id)
            entry: int = self.connection.execute(
                f"SELECT COUNT(*) from queue").fetchone()[0] + 1
            numAhead: int = self.queue.offer(self.getName(
                message.author.id), message.content, entry, message.author.id)
            self.connection.execute(f"""INSERT INTO queue (entry, discordID, username, reason, timeEntered) VALUES
                ({entry}, {message.author.id}, \"{username}\", \"{self.escapeString(message.content)}\", 
                \"{str(datetime.datetime.now())}\")""")
            self.connection.commit()

        await message.reply(f"<@{message.author.id}>: You're now in the queue. " + ("There are " + str(numAhead) + " people" if numAhead != 1 else "There is 1 person") + " ahead of you.")
        await self.client.get_user(self.benderID).send(name + " just entered queue: " + message.content)

    def start(self):
        """ Updates the queue database to mark the current student as having started."""
        self.current.startTime = datetime.datetime.now()
        with threading.Lock():
            self.connection.execute(
                f"""UPDATE queue SET timeStart = \"{self.current.startTime}\" where entry = {self.current.entry}""")
            self.connection.commit()

    def finish(self):
        """ Updates the queue database to mark the current student as finished."""
        with threading.Lock():
            self.connection.execute(
                f"""UPDATE queue SET timeLength = {round((datetime.datetime.now() - self.current.startTime).total_seconds()/60)} where entry = {self.current.entry}""")
            self.connection.commit()

    async def getReason(self, message: Message):
        """ Asks the sender of the given message for a brief summary of their 
            question"""
        await message.reply(f"<@{message.author.id}>: Please briefly describe your question.")
        with threading.Lock():
            self.waitingForReply[message.author.id] = "getQuestion"

    def isRegistered(self, id: int) -> bool:
        """ Returns true if the given discordID has been registered in the 
            database, otherwise returns false"""
        return self.connection.execute(f"""SELECT COUNT(*) FROM users 
            WHERE discordID = {id}""").fetchone()[0] > 0

    def getColbyUsername(self, id: int) -> str:
        """ Gets the Colby username from the database of the person with the given 
            discord ID"""
        return self.connection.execute(f"""SELECT (username) FROM users 
            WHERE discordID = {id}""").fetchone()[0]

    def getName(self, id: int) -> str:
        """ Gets the name from the database of the person with the given discord 
            ID"""
        return self.connection.execute(f"""SELECT (name) FROM users 
            WHERE discordID = {id}""").fetchone()[0]

    def registerEvents(self):
        """ Registers all the events the bot cares about. For this projects, 
            that's really just reading messages that start with $, followed by
            a specific keyword."""

        @self.client.event
        async def on_message(message: Message):
            """ This function is called whenever a message is read by this 
                bot"""

            # Ignore bot's own messages
            if message.author == self.client.user:
                pass

            elif message.content.startswith("$") and type(message.channel) != discord.channel.DMChannel:
                reply: discord.message.Message = await message.reply(f"To avoid clutter, please DM me instead. You can DM me by clicking my name on the bar on the right.")
                await message.delete(delay = 10)
                await reply.delete(delay = 10)

            elif message.content.startswith("$status"):
                await message.reply(f"Current queue length: {self.queue.size}")
                if self.isRegistered(message.author.id) and self.queue.__contains__(self.getName(message.author.id)):
                    index: int = self.queue.findPosition(message.author.id)
                    await message.reply(f"Students ahead of you: {index}")

            elif message.content.startswith("$enterQueue"):
                await self.queueCommand(message)

            elif message.content.startswith("$finish"):
                if (message.author.id == self.benderID):
                    if self.current != None:
                        self.finish()
                    else:
                        await message.reply("No current user")
                else:
                    await message.reply("You're not Bender :p")

            elif message.content.startswith("$next"):
                if (message.author.id == self.benderID):
                    if self.current != None:
                        self.finish()
                    self.current = self.queue.poll()
                    if (self.current == None):
                        await message.reply("No user in queue")
                    else:
                        await message.reply("The next user is " + self.current.name + ": " + self.current.reason)
                        nextUser: discord.User = self.client.get_user(
                            self.current.discordID)
                        await nextUser.send(f"You're up! Please head to Max's office")
                        self.start()
                        nextInLine: discord.User = self.client.get_user(
                            self.queue.start.discordID) if self.queue.start != None else None
                        if nextInLine != None:
                            await nextInLine.send(f"You're next in line, if you aren't in Davis please head over.")
                else:
                    message.reply(
                        f"<@{message.author.id}>: You're not Bender :p")

            elif message.author.id in self.waitingForReply:
                if self.waitingForReply.get(message.author.id) == "username":
                    if (message.content.lower() in self.validUsers):
                        await message.reply(f"<@{message.author.id}>: Great, I've paired your discord id to your Colby username.")
                        await self.registerUser(message.author.id, message.content.lower())
                        await self.getReason(message)
                    else:
                        await message.reply(f"<@{message.author.id}>: username not found, check your spelling")
                elif self.waitingForReply.get(message.author.id) == "getQuestion":
                    with threading.Lock():
                        self.waitingForReply.__delitem__(message.author.id)
                    await self.enterQueue(message)


if __name__ == "__main__":
    Master_Bot()
