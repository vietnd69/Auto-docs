---
id: class
title: Class
description: Provides an object-oriented class system with inheritance, property getters/setters, and optional instance tracking for Lua in Don't Starve Together.
tags: [core, utility, oop]
sidebar_position: 10

last_updated: 2026-03-20
build_version: 714014
change_status: stable
category_type: root
source_hash: 54cf8ca7
system_scope: entity
---

# Class

> Based on game build **714014** | Last updated: 2026-03-20

## Overview
`class.lua` implements a foundational object-oriented programming system for Lua within Don't Starve Together. It provides class creation with inheritance support, property management with custom getters and setters, read-only property enforcement, and optional instance tracking for debugging memory leaks. This utility is used throughout the codebase to define components, stategraphs, brains, and other core systems. Unlike typical components, this is a meta-system that enables the class pattern used by nearly all other scripts.

## Usage example
```lua
local MyClass = Class(function(self, name, value)
    self.name = name
    self.value = value
end)

local instance = MyClass("test", 42)
print(instance.name) -- "test"

local ChildClass = Class(MyClass, function(self, name, value, extra)
    self._super(name, value)
    self.extra = extra
end)

local child = ChildClass("child", 100, "bonus")
print(child:is_a(MyClass)) -- true
```

## Dependencies & tags
**Components used:** None identified. This is a core utility module with no external component dependencies.
**Tags:** None identified. This module does not interact with the entity tag system.

## Properties
| Property | Type | Default Value | Description |
|----------|------|---------------|-------------|
| `_ctor` | function | `nil` | The constructor function passed during class creation. |
| `_base` | table | `nil` | Reference to the parent class when using inheritance. |
| `__index` | function | varies | Metamethod for property access, supports custom property getters. |
| `__newindex` | function | varies | Metamethod for property assignment, supports custom property setters. |
| `is_a` | function | `_is_a` | Method to check if an instance is descended from a class. |
| `is_class` | function | `_is_class` | Method to check if a table is a class definition rather than an instance. |
| `is_instance` | function | varies | Method to check if an object is an instance of the class. |

## Main functions
### `Class(base, _ctor, props)`
*   **Description:** Creates a new class with optional inheritance from a base class, a constructor function, and property definitions. Returns a callable class table that can be invoked to create instances.
*   **Parameters:** `base` (table or function) - Optional parent class to inherit from, or constructor function if no inheritance. `_ctor` (function) - Constructor called when creating instances. `props` (table) - Optional property definitions with custom setters.
*   **Returns:** A class table that can be called like a function to instantiate objects.
*   **Error states:** If `props` is provided but the class does not support property setters, assertions will fail when attempting to use `makereadonly` or `addsetter`.

### `makereadonly(t, k)`
*   **Description:** Converts a property into a read-only property that cannot be modified after initialization. Attempts to change the value will trigger an assertion error.
*   **Parameters:** `t` (table) - The class or instance table. `k` (string) - The property key to make read-only.
*   **Returns:** Nothing.
*   **Error states:** Asserts if the class does not support read-only properties (requires `props` table in `Class` constructor). Asserts if attempting to assign a different value to the read-only property.

### `addsetter(t, k, fn)`
*   **Description:** Registers a custom setter function for a property. The setter is called whenever the property value changes, allowing validation or side effects.
*   **Parameters:** `t` (table) - The class or instance table. `k` (string) - The property key. `fn` (function) - The setter function with signature `fn(table, newValue, oldValue)`.
*   **Returns:** Nothing.
*   **Error states:** Asserts if the class does not support property setters (requires `props` table in `Class` constructor).

### `removesetter(t, k)`
*   **Description:** Removes a custom setter from a property, restoring default assignment behavior.
*   **Parameters:** `t` (table) - The class or instance table. `k` (string) - The property key.
*   **Returns:** Nothing.
*   **Error states:** Silently returns if no setter exists for the specified key.

### `ReloadedClass(mt)`
*   **Description:** Removes a class from the `ClassRegistry` when hot-reloading code. Used internally during development to clean up stale class references.
*   **Parameters:** `mt` (table) - The metatable of the class to remove.
*   **Returns:** Nothing.

### `HandleClassInstanceTracking()`
*   **Description:** Debug function that prints the top 10 classes by instance count when `TrackClassInstances` is enabled. Called periodically to help identify memory leaks or excessive instantiation.
*   **Parameters:** None.
*   **Returns:** Nothing.
*   **Error states:** Only produces output when `TrackClassInstances` is set to `true` and `CWD` is defined. Otherwise silently returns.

### `is_a(obj, klass)`
*   **Description:** Checks if an object is an instance of a class or any of its parent classes through the inheritance chain.
*   **Parameters:** `obj` (table) - The object to check. `klass` (table) - The class to test against.
*   **Returns:** `true` if the object inherits from the class, `false` otherwise.

### `is_class(self)`
*   **Description:** Determines if a table is a class definition rather than an instance.
*   **Parameters:** `self` (table) - The table to check.
*   **Returns:** `true` if the table is a class, `false` if it is an instance.

## Events & listeners
Not applicable. This module does not use the entity event system.