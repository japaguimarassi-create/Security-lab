# Enturma AI — Forge 1.20.1

This isolated branch contains the Enturma AI Minecraft Forge 1.20.1 source and the GitHub Actions build for it.

Commands:
- `/chat local <texto>` — send a message to the nearest allowed mob within the configured conversation radius.
- `/chat global <texto>` — send a message to eligible mobs loaded within the server view-distance radius.
- `/enturma status` — show the current AI and mob-selection status.
- `/enturma reload` — reload the allowed-mob list (permission level 2).

The workflow uses Java 17 and Gradle 8.8, updates the source to 0.3.1 with queue safeguards, compiles/reobfuscates the mod, validates mod metadata and both chat commands, and uploads only the compiled JAR.
