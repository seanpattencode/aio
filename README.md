# AIOS
Will one day save the world. Possibly today.

Basic explanation:
This project will allow for an extensible, modular, system of running automation workflows, AI tasks, and anything else a user might desire to run, allowing them to become the manager of an automated system. Done right, this should fundamentally tie the capabilities of the user through tool use to advancements in technology, such as ai algorithm developments, computing hardware and software developments, and other related things more seamlessly than current operating systems and applications allow for. It should be easy enough for someone with no computer skill to use, and sophisticated enough that a user could build thier own programs on it, and modify and enhance the base programs. Without something such as this, it is perhaps almost inevitable that humans will become irelevant to the future of intelligent civilization, and the development of this project must be made in view of improving the capabilities of civlization and finding geniune value and a role for humans and other sentient beings in the future. At the very least, it seems inevitable that something like this will have to exist for the sake of coordinating and revewing work by AI systems, and so it must be built for that reason alone with the preference that it be built with more beneficial effects than the simple inevitability will lead to be whatever ends up existing. 

Project architecture:
The architecture must be extermely portable and simple, extensible, and able to run almost everwhere, yet also be easy as possible to develop in especially in the early stages.
Therefore the minimal architectural design choices are:
No system of rules is perfectly true or self consistent, so minor violations must be allowed.
To extensively use docker in slim mode.
To have just one database to start with that handles everything related to persistence for user, while the programs otherwise are stateless. This may change later.
A strong preference for python but not more than that.
Don't add more rules than these.

How to run:






