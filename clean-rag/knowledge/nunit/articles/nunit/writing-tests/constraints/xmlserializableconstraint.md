<!-- Source: github.com/nunit/docs/docs/articles\nunit\writing-tests\constraints\XmlSerializableConstraint.md | Tier: A | Topic: nunit | Fetched: 2026-06-26 -->

---
uid: constraint-xmlserializable
---

# XmlSerializable Constraint

`XmlSerializableConstraint` tests whether an object is serializable in XML format.

## Constructor

```csharp
XmlSerializableConstraint()
```

## Syntax

```csharp
Is.XmlSerializable
```

## Examples of Use

```csharp
Assert.That(someObject, Is.XmlSerializable));
```

## See also

* [BinarySerializableConstraint](BinarySerializableConstraint.md)
