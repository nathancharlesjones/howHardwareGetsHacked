# Application Code

## Competition requirements

In the 2023 MITRE eCTF, teams were asked to provide firmware for a simulated car and key fob system. Their final deliverable needed to be able to build three images:
- Car
- Paired fob (comes "from the manufacturer" ready to unlock an associated car)
- Unpaired fob

![Build process](../docs/images/buildProcess.png)

These devices (along with, possibly, any custom host-side tools), were required to be able to do three things:

### Unlock a car

With a car, paired fob, and computer connected as shown below, pressing the on-board button should cause the car to send the "unlock" flag to the computer, along with the flags for any features that have been been enabled on the fob.

![Unlocking](../docs/images/unlockSetup.png)

### Pair an unpaired fob

With a paired fob, unpaired fob, and computer connected as shown below, sending `pair <PIN>\n` to the paired fob should cause it to send the necessary information to the unpaired fob to let it unlock the associated car. The paired fob does not transfer its enabled features.

![Pairing](../docs/images/pairFobSetup.png)

### Package and subsequently enable a new feature

Running the "package tool" results in a binary feature file.

![Packaging](../docs/images/packageFeatureSetup.png)

With a paired fob and computer connected as shown below, sending `enable <BIN>\n` results in the fob enabling that feature. Subsequent unlock attempts with that fob will cause the car to send the associated feature flag to the attached computer.

`<BIN>` represents the contents of the previously-packaged binary feature file, encoded as ASCII hex digits (i.e. `\xA5` [`0b10100101`] would be sent as ASCII `A` `5` [`0b01000001 0b00110101`]).

![Enabling](../docs/images/enableFeatureSetup.png)

## The current firmware

### Fob

![Fob flowchart](../docs/images/fobFlowchart.png)

### Car

![Car flowchart](../docs/images/carFlowchart.png)

### Unlock sequence diagram

![Unlock sequence diagram](../docs/images/)

### Pairing sequence diagram

![Pairing sequence diagram](../docs/images/)

### Enabling sequence diagram

![Enabling sequence diagram](../docs/images/)