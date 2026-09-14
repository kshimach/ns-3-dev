/*
 * Copyright (c) 2009 University of Washington
 *
 * SPDX-License-Identifier: GPL-2.0-only
 */

/* taken from src/node/ipv4-routing-protocol.h and adapted to IPv6 */

#ifndef IPV6_ROUTING_PROTOCOL_H
#define IPV6_ROUTING_PROTOCOL_H

#include "ipv6-header.h"
#include "ipv6-interface-address.h"
#include "ipv6.h"

#include "ns3/callback.h"
#include "ns3/nstime.h"
#include "ns3/object.h"
#include "ns3/output-stream-wrapper.h"
#include "ns3/packet.h"
#include "ns3/socket.h"

namespace ns3
{

class Ipv6MulticastRoute;
class Ipv6Route;
class NetDevice;

/**
 * @ingroup internet
 * @defgroup ipv6Routing IPv6 Routing Protocols.
 *
 * The classes in this group implement different routing protocols
 * for IPv6. Other modules could implement further protocols.
 */

/**
 * @ingroup ipv6Routing
 * @brief Abstract base class for IPv6 routing protocols.
 *
 * Defines two virtual functions for packet routing and forwarding.  The first,
 * RouteOutput (), is used for locally originated packets, and the second,
 * RouteInput (), is used for forwarding and/or delivering received packets.
 * Also defines the signatures of four callbacks used in RouteInput ().
 */

class Ipv6RoutingProtocol : public Object
{
  public:
    /**
     * @brief Get the type ID.
     * @return the object TypeId
     */
    static TypeId GetTypeId();

    /// Callback for unicast packets to be forwarded
    typedef Callback<void,
                     Ptr<const NetDevice>,
                     Ptr<Ipv6Route>,
                     Ptr<const Packet>,
                     const Ipv6Header&>
        UnicastForwardCallback;

    /// Callback for multicast packets to be forwarded
    typedef Callback<void,
                     Ptr<const NetDevice>,
                     Ptr<Ipv6MulticastRoute>,
                     Ptr<const Packet>,
                     const Ipv6Header&>
        MulticastForwardCallback;

    /// Callback for packets to be locally delivered
    typedef Callback<void, Ptr<const Packet>, const Ipv6Header&, uint32_t> LocalDeliverCallback;

    /// Callback for routing errors (e.g., no route found)
    typedef Callback<void, Ptr<const Packet>, const Ipv6Header&, Socket::SocketErrno> ErrorCallback;

    /**
     * @brief Query routing cache for an existing route, for an outbound packet
     *
     * This lookup is used by transport protocols.  It does not cause any
     * packet to be forwarded, and is synchronous.  Can be used for
     * multicast or unicast.  The Linux equivalent is ip_route_output ()
     *
     * @param p packet to be routed.  Note that this method may modify the packet.
     *          Callers may also pass in a null pointer.
     * @param header input parameter (used to form key to search for the route)
     * @param oif Output interface device.  May be zero, or may be bound via
     *            socket options to a particular output interface.
     * @param sockerr Output parameter; socket errno
     *
     * @returns a code that indicates what happened in the lookup
     */
    virtual Ptr<Ipv6Route> RouteOutput(Ptr<Packet> p,
                                       const Ipv6Header& header,
                                       Ptr<NetDevice> oif,
                                       Socket::SocketErrno& sockerr) = 0;

    /**
     * @brief Route an input packet (to be forwarded or locally delivered)
     *
     * This lookup is used in the forwarding process.  The packet is
     * handed over to the Ipv6RoutingProtocol, and will get forwarded onward
     * by one of the callbacks.  The Linux equivalent is ip_route_input ().
     * There are four valid outcomes, and a matching callbacks to handle each.
     *
     * @param p received packet
     * @param header input parameter used to form a search key for a route
     * @param idev Pointer to ingress network device
     * @param ucb Callback for the case in which the packet is to be forwarded
     *            as unicast
     * @param mcb Callback for the case in which the packet is to be forwarded
     *            as multicast
     * @param lcb Callback for the case in which the packet is to be locally
     *            delivered
     * @param ecb Callback to call if there is an error in forwarding
     * @returns true if the Ipv6RoutingProtocol takes responsibility for
     *          forwarding or delivering the packet, false otherwise
     */
    virtual bool RouteInput(Ptr<const Packet> p,
                            const Ipv6Header& header,
                            Ptr<const NetDevice> idev,
                            const UnicastForwardCallback& ucb,
                            const MulticastForwardCallback& mcb,
                            const LocalDeliverCallback& lcb,
                            const ErrorCallback& ecb) = 0;

    /**
     * @brief Notify when specified interface goes UP.
     *
     * Protocols are expected to implement this method to be notified of the state change of
     * an interface in a node.
     * @param interface the index of the interface we are being notified about
     */
    virtual void NotifyInterfaceUp(uint32_t interface) = 0;

    /**
     * @brief Notify when specified interface goes DOWN.
     *
     * Protocols are expected to implement this method to be notified of the state change of
     * an interface in a node.
     * @param interface the index of the interface we are being notified about
     */
    virtual void NotifyInterfaceDown(uint32_t interface) = 0;

    /**
     * @brief Notify when specified interface add an address.
     *
     * Protocols are expected to implement this method to be notified whenever
     * a new address is added to an interface. Typically used to add a 'network route' on an
     * interface. Can be invoked on an up or down interface.
     * @param interface the index of the interface we are being notified about
     * @param address a new address being added to an interface
     */
    virtual void NotifyAddAddress(uint32_t interface, Ipv6InterfaceAddress address) = 0;

    /**
     * @brief Notify when specified interface add an address.
     *
     * Protocols are expected to implement this method to be notified whenever
     * a new address is removed from an interface. Typically used to remove the 'network route' of
     * an interface. Can be invoked on an up or down interface.
     * @param interface the index of the interface we are being notified about
     * @param address a new address being added to an interface
     */
    virtual void NotifyRemoveAddress(uint32_t interface, Ipv6InterfaceAddress address) = 0;

    /**
     * @brief Notify a new route.
     *
     * Typically this is used to add another route from IPv6 stack (i.e. ICMPv6
     * redirect case, ...).
     * @param dst destination address
     * @param mask destination mask
     * @param nextHop nextHop for this destination
     * @param interface output interface
     * @param prefixToUse prefix to use as source with this route
     */
    virtual void NotifyAddRoute(Ipv6Address dst,
                                Ipv6Prefix mask,
                                Ipv6Address nextHop,
                                uint32_t interface,
                                Ipv6Address prefixToUse = Ipv6Address::GetZero()) = 0;

    /**
     * @brief Notify route removing.
     * @param dst destination address
     * @param mask destination mask
     * @param nextHop nextHop for this destination
     * @param interface output interface
     * @param prefixToUse prefix to use as source with this route
     */
    virtual void NotifyRemoveRoute(Ipv6Address dst,
                                   Ipv6Prefix mask,
                                   Ipv6Address nextHop,
                                   uint32_t interface,
                                   Ipv6Address prefixToUse = Ipv6Address::GetZero()) = 0;

    /**
     * @brief Typically, invoked directly or indirectly from ns3::Ipv6::SetRoutingProtocol
     * @param ipv6 the ipv6 object this routing protocol is being associated with
     */
    virtual void SetIpv6(Ptr<Ipv6> ipv6) = 0;

    /**
     * @brief Print the Routing Table entries
     *
     * @param stream The ostream the Routing table is printed to
     * @param unit The time unit to be used in the report
     */
    virtual void PrintRoutingTable(Ptr<OutputStreamWrapper> stream,
                                   Time::Unit unit = Time::S) const = 0;

    /**
     * @brief Give a routing protocol the chance to modify a packet it just
     *        routed with RouteOutput(), before it is handed to the device.
     *
     * This runs only at the node that originates the packet, once per packet,
     * immediately before it leaves Ipv6L3Protocol::Send(). The default does
     * nothing. A protocol that needs to add an IPv6 extension header can do so
     * here: change the packet and, if the extension changes what follows the
     * IPv6 header, header's next header field, here; Ipv6L3Protocol::Send()
     * recomputes the payload length from the packet afterwards, so this is the
     * one place in ns-3 where a routing protocol can put an extension header
     * onto a packet at the point it originates, something RouteOutput() cannot
     * do since the packet it is handed is still headerless at that point and
     * the IPv6 header ns-3 builds around the two calls is otherwise fixed.
     *
     * This is not called again as the packet is forwarded at each subsequent
     * hop: a routing header meant to be consumed hop-by-hop has to arrange
     * that itself, e.g. through an Ipv6ExtensionRouting registered on the
     * Ipv6ExtensionRoutingDemux, the way Ipv6ExtensionLooseRouting does for
     * RFC 6554's predecessor, the Type 0 Routing Header.
     *
     * @param packet the packet as it will be sent, without the IPv6 header
     * @param header the IPv6 header that will be prepended; the next header
     *               field is not used yet and read on return
     * @param route the route RouteOutput() returned for this packet
     */
    virtual void PrepareOutgoingPacket(Ptr<Packet> packet, Ipv6Header& header, Ptr<Ipv6Route> route);
};

} // namespace ns3

#endif /* IPV6_ROUTING_PROTOCOL_H */
