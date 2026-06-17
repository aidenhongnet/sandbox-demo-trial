# Prefixes

A prefix is an IPv4 or IPv6 network and mask expressed in CIDR notation (e.g. 192.0.2.0/24). A prefix entails only the "network portion" of an IP address: All bits in the address not covered by the mask must be zero. (In other words, a prefix cannot be a specific IP address.) Prefixes are automatically organized by their parent aggregate and assigned VRF.

## Fields

### Prefix

The IPv4 or IPv6 network this prefix represents.

### Status

The prefix's operational status. Note that the status of a prefix does _not_ have any impact on its member IP addresses, which may have their statuses defined independently. The "container" status indicates that the prefix exists merely as a container for organizing child prefixes.

Additional statuses may be defined by setting `Prefix.status` under the `FIELD_CHOICES` configuration parameter.

### VRF

The Virtual Routing and Forwarding instance in which this prefix exists.

VRF assignment is optional. Prefixes with no VRF assigned are considered to exist in the "global" table.

### Role

The user-defined functional role assigned to the prefix.

### Is a Pool

Designates whether the prefix should be treated as a pool. If selected, the first and last IP addresses within the prefix (normally reserved as the network and broadcast addresses, respectively) will be considered usable. This option is ideal for documenting NAT pools.

### Mark Utilized

If selected, this prefix will report 100% utilization regardless of how many child objects have been defined within it.

### Scope

This field replaced the `site` field in NetBox v4.2.

The region, site, site group or location to which the prefix is assigned (optional).

### VLAN

The VLAN to which this prefix is assigned (optional). This mapping is helpful for associating IP space with layer two domains. A VLAN may have multiple prefixes assigned to it.
