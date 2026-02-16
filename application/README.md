# Application Code

## Competition requirements

In the 2023 MITRE eCTF, teams were asked to provide firmware for a simulated car and key fob system. Their final deliverable needed to be able to build three images:
- Car
- Paired fob (comes "from the manufacturer" ready to unlock an associated car)
- Unpaired fob

![Build process](docs/images/buildProcess.png)

These devices (along with, possibly, any custom host-side tools), were required to be able to do three things:

### Unlock a car
![Unlocking](docs/images/unlockSetup.png)

### Pair an unpaired fob
![Pairing](docs/images/pairFobSetup.png)

### Package and subsequently enable a new feature
![Packaging](docs/images/packageFeatureSetup.png)

![Enabling](docs/images/enableFeatureSetup.png)

## The current firmware

### Fob

![Flowchart](docs/images/)

### Car

![Flowchart](docs/images/)

### Unlock sequence diagram

![Flowchart](docs/images/)

### Pairing sequence diagram

![Flowchart](docs/images/)

### Enabling sequence diagram