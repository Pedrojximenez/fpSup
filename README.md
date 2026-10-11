fpSup — Research & Development
Open firmware research, development tools, and community-driven modifications for the SIGMA fp.
fpSup began as an independent effort to explore the hidden capabilities of the SIGMA fp.
What started with firmware reverse engineering has gradually grown into a community of developers exploring sensor modes, CinemaDNG recording, lossless compression, gyroscope stabilization, autofocus, and much more.
This repository is where I share my research notes, development tools, source code, experiments, and discoveries.
My goal is to make it easier for others to continue exploring without having to start from scratch.
Resources
- fpSup Website: https://ijigen.github.io/fpSup/
- Discord: https://discord.gg/BAYRA7Zb5
- Support Development: https://ko-fi.com/fpsup
Open Research
I intend to make my development research, notes, and source code publicly available.
This includes:
- Firmware reverse-engineering findings
- Development tools and workflows
- Memory addresses, firmware structures, and technical discoveries
- Sensor modes and imaging pipeline research
- Source code and experimental implementations
- AI-assisted development notes and research history
- Failed experiments, limitations, and unresolved problems
I believe sharing the research process is just as important as sharing the final result.
A compiled binary may tell you what a program does, but it doesn't necessarily explain why it was designed that way, what was tried before, or which problems have already been investigated.
With AI-assisted development, these details are especially valuable.
I hope this repository can save other developers from spending countless hours — and AI tokens — rediscovering the same things.
Some materials may be incomplete, experimental, outdated, or poorly organized. Please treat them as research references rather than definitive documentation.
Development Philosophy
Independent Development
I believe everyone should be free to develop in whatever way they enjoy most.
Different developers may approach the same problem using completely different architectures, tools, or algorithms.
That's a good thing.
Independent approaches allow us to explore more possibilities, compare results, and learn from each other's discoveries.
There is no need for everyone to follow a single development direction.
Voluntary Sharing
I encourage developers to voluntarily share their findings, research notes, source code, and experiences.
However, sharing is entirely up to each individual.
Nobody is required to publish their work or follow a particular development model.
I will continue sharing my own research as openly as I can.
Collaboration Through AI
AI has fundamentally changed how independent development can work.
Developers no longer need to use identical tools, environments, or codebases to learn from each other's work.
Research notes, source code, and development logs can be shared between AI-assisted workflows, allowing discoveries to be understood and integrated much more efficiently.
I am particularly interested in collaboration through shared development logs, such as worklog.md, where different developers and their AI assistants can exchange progress without constantly repeating the same analysis.
I believe the future of development will involve much more independent exploration and much easier integration of shared knowledge.
Contributions & Pull Requests
Why I Generally Don't Accept PRs
I truly appreciate everyone who wants to contribute to fpSup.
However, I generally do not accept external pull requests into my main development repository.
This is not because I want to control the project or discourage contributions.
My concern is maintenance responsibility.
When someone else's code becomes part of my repository, I feel responsible for keeping it working, maintaining compatibility, reviewing changes, and fixing problems.
Unfortunately, I simply don't have the capacity to maintain everything.
I'm also not particularly good at managing large collaborative Git workflows.
How You Can Contribute
You are welcome to develop and maintain your own Sup independently.
You can publish your work through your own GitHub repository, website, or another platform.
Where appropriate, fpSup may link to your project or make compatible releases available through fpSup-Merge, with proper attribution.
Ideally, each developer remains responsible for maintaining their own implementation.
This allows everyone to contribute without creating unnecessary obligations for others.
Integration does not have to mean transferring ownership or maintenance responsibility.
fpSup-Merge & Modular Development
One of my goals is to make independently developed Sup modules easier to combine.
The newer fpSup architecture separates Sups into individual binary modules, reducing the need to manually merge large amounts of code.
My long-term vision is for fpSup-Merge to discover compatible modules from independent repositories.
Developers could then maintain their own releases while users access them through a shared interface.
The goal is simple:
Develop independently. Share voluntarily. Integrate easily.
I also want to avoid imposing unnecessary rules on how individual Sups should be implemented.
Whenever possible, shared infrastructure should provide capabilities without dictating how developers must use them.
Credits & Attribution
Every developer's work is unique.
I believe contributions should be credited to the people who actually made them, even when their work is distributed through fpSup.
The community already includes developers exploring different approaches to sensor modes, compression, stabilization, monitoring, and many other features.
I hope everyone can continue developing in their own direction and sharing their discoveries.
There is no need for anyone's work to be overshadowed by the project that brings it together.
Experimental Software & Risks
fpSup involves experimental firmware modifications and reverse engineering.
These modifications are not official SIGMA features.
They may cause unexpected behavior, recording failures, data corruption, persistent setting problems, or camera instability.
Some experiments may carry a risk of rendering the camera unusable.
Please understand the risks before using experimental builds.
Research notes and code may contain mistakes or unverified assumptions.
Do not assume that a published experiment has been fully tested or is safe for general use.
Why I Created This Community
I don't know how long fpSup will remain relevant.
AI is advancing rapidly. Perhaps five years from now, many of the problems we're solving today will be things anyone can figure out simply by talking to their own AI.
Maybe projects like fpSup won't even be necessary anymore.
And that's okay.
Because the technical achievements were never the only reason I wanted to build this community.
The research, the experiments, the failures, the discoveries, and the people I've met along the way have become something much more meaningful to me.
I want to create connections between people.
I hope everyone can enjoy exploring, creating, and sharing in their own way.
And if the work I've shared helps someone else discover something new, that alone makes me happy.
Thank you to everyone who has been part of this journey.
— bei / 夏曉雨 / ijigen ❤️
