- 1 sentence/paragraph summary of the project + links to articles
	- Purpose is to accompany the articles, demonstrate iterative attacks on and defenses for the 2023 MITRE eCTF competition
	- I built this project instead of using the 2023 insecure example because I didn't want to use Docker, I wanted multi-platform support, and I wanted quality-of-life features like automated testing and x86 simulations.
- Summary of project tree/structure
	- Discuss hardware abstraction and show @/home/nathancharlesjones/Documents/Work/DigiKey/2026/articles/howHardwareGetsHacked_Part3/hwAbstraction.png
- 1 sentence/paragraph description of 2023 eCTF competition (defer specifics of car/fob flowcharts, sequence diagrams, etc to another README in the application folder)
- Navigating the commits
	- I'm anticipating that development of this project will look like: demonstrate an attack, make a branch, implement defense, verify defense works, merge with main. So people who land on this README are likely looking at the most up-to-date version, even if they're just starting out reading the articles. So I'm thinking this section is a summary of the defenses I've implemented with links to those merges, e.g.
	1) (Baseline project)[commit #xxxxxx]
	2) (Defending against code readout)[commit #xxxxxx]
	3) (Defending against replay attacks)[commit #xxxxxx]
	etc
- Usage
	- Read the articles. Find the right commit, see it break, then see the fix or implement your own defense.
	- Setup (mention setup.md files)
	- Show workflow diagram here (@/home/nathancharlesjones/Documents/Work/DigiKey/2026/articles/howHardwareGetsHacked_Part3/pipeline.png)
	- Building
		- Abbreviated build instructions
		- Show scons commands/format
	- Flashing/running
		- Abbreviated instructions for using "openocd.py flash" and "simulate.py"
	- Testing/debugging
		- Abbreviated instructions for using "monitor.py", test commands, pytest, and "openocd.py debug"
		- Show testing diagram (@/home/nathancharlesjones/Documents/Work/DigiKey/2026/articles/howHardwareGetsHacked_Part3/testSetup.png)
- Adding new tests
- Adding a new platform
	- Instructions for adding a new platform, organized by tool, e.g.
	- Integrating with scons (probably not too hard)
	- Integrating with openocd.py (maybe not too hard, assuming openocd support exists? harder if it doesn't)
	- Integrating with list.py
	- Integrating with conftest.py (harder, even if openocd support exists, I think. much harder if openocd support doesn't exist)
	- Am I missing anything?