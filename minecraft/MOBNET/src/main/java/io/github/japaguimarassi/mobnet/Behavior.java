// SPDX-FileCopyrightText: 2025 owlmaddie LLC
// SPDX-License-Identifier: GPL-3.0-or-later
// Adapted from CreatureChat; see NOTICE.md.
package io.github.japaguimarassi.mobnet;

public class Behavior {
    private final String name;
    private final Integer argument;

    public Behavior(String name, Integer argument) {
        this.name = name;
        this.argument = argument;
    }

    public String getName() {
        return name;
    }

    public Integer getArgument() {
        return argument;
    }

    @Override
    public String toString() {
        return argument == null ? name : name + ": " + argument;
    }
}
