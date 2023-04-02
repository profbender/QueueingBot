# Queueing Bot

A Discord bot for handling my office hours. 

My office hours tend to get somewhat hectic so this bot is designed to help the flow. As there's a wide variability to how long individual questions take in my office hours, appointments don't really make sense, so a bot that would tell students when their turn was coming up seemed like a more reasonable approach.

This bot supports the following commands (the $ is part of the command) for all users:
* __$enterQueue__: enters the user into the queue.
* __$status__: returns the number of users in the queue. If the user is already in the queue, also returns the number of other users ahead of them.

This bot supports the following commands for the professor: 
* __$next__: Returns and removes the user at the front of the queue. If a user is currently marked as meeting with the professor, marks them as finished.
* __$finish__: Marks the user currently meeting with the professor as finished.

---

This bot communicates with a SQLite database in the same folder for recording a mapping of discordIDs to names and ColbyIDs as well a history of the data in the queue.