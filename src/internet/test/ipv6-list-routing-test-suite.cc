/*
 * Copyright (c) 2009 University of Washington
 *
 * SPDX-License-Identifier: GPL-2.0-only
 *
 */

#include "ns3/ipv6-list-routing.h"
#include "ns3/ipv6-route.h"
#include "ns3/ipv6-routing-protocol.h"
#include "ns3/test.h"

namespace ns3
{

/**
 * @ingroup internet-test
 *
 * @brief IPv6 dummy routing class (A)
 */
class Ipv6ARouting : public Ipv6RoutingProtocol
{
  public:
    Ptr<Ipv6Route> RouteOutput(Ptr<Packet> p,
                               const Ipv6Header& header,
                               Ptr<NetDevice> oif,
                               Socket::SocketErrno& sockerr) override
    {
        return nullptr;
    }

    bool RouteInput(Ptr<const Packet> p,
                    const Ipv6Header& header,
                    Ptr<const NetDevice> idev,
                    const UnicastForwardCallback& ucb,
                    const MulticastForwardCallback& mcb,
                    const LocalDeliverCallback& lcb,
                    const ErrorCallback& ecb) override
    {
        return false;
    }

    void NotifyInterfaceUp(uint32_t interface) override
    {
    }

    void NotifyInterfaceDown(uint32_t interface) override
    {
    }

    void NotifyAddAddress(uint32_t interface, Ipv6InterfaceAddress address) override
    {
    }

    void NotifyRemoveAddress(uint32_t interface, Ipv6InterfaceAddress address) override
    {
    }

    void NotifyAddRoute(Ipv6Address dst,
                        Ipv6Prefix mask,
                        Ipv6Address nextHop,
                        uint32_t interface,
                        Ipv6Address prefixToUse = Ipv6Address::GetZero()) override
    {
    }

    void NotifyRemoveRoute(Ipv6Address dst,
                           Ipv6Prefix mask,
                           Ipv6Address nextHop,
                           uint32_t interface,
                           Ipv6Address prefixToUse) override
    {
    }

    void SetIpv6(Ptr<Ipv6> ipv6) override
    {
    }

    void PrintRoutingTable(Ptr<OutputStreamWrapper> stream, Time::Unit unit) const override
    {
    }

    void PrepareOutgoingPacket(Ptr<Packet> packet,
                               Ipv6Header& header,
                               Ptr<Ipv6Route> route) override
    {
        m_prepareOutgoingCalled = true;
    }

    bool m_prepareOutgoingCalled = false; //!< set when PrepareOutgoingPacket() is called
};

/**
 * @ingroup internet-test
 *
 * @brief IPv6 dummy routing class (B)
 */
class Ipv6BRouting : public Ipv6RoutingProtocol
{
  public:
    Ptr<Ipv6Route> RouteOutput(Ptr<Packet> p,
                               const Ipv6Header& header,
                               Ptr<NetDevice> oif,
                               Socket::SocketErrno& sockerr) override
    {
        return nullptr;
    }

    bool RouteInput(Ptr<const Packet> p,
                    const Ipv6Header& header,
                    Ptr<const NetDevice> idev,
                    const UnicastForwardCallback& ucb,
                    const MulticastForwardCallback& mcb,
                    const LocalDeliverCallback& lcb,
                    const ErrorCallback& ecb) override
    {
        return false;
    }

    void NotifyInterfaceUp(uint32_t interface) override
    {
    }

    void NotifyInterfaceDown(uint32_t interface) override
    {
    }

    void NotifyAddAddress(uint32_t interface, Ipv6InterfaceAddress address) override
    {
    }

    void NotifyRemoveAddress(uint32_t interface, Ipv6InterfaceAddress address) override
    {
    }

    void NotifyAddRoute(Ipv6Address dst,
                        Ipv6Prefix mask,
                        Ipv6Address nextHop,
                        uint32_t interface,
                        Ipv6Address prefixToUse = Ipv6Address::GetZero()) override
    {
    }

    void NotifyRemoveRoute(Ipv6Address dst,
                           Ipv6Prefix mask,
                           Ipv6Address nextHop,
                           uint32_t interface,
                           Ipv6Address prefixToUse) override
    {
    }

    void SetIpv6(Ptr<Ipv6> ipv6) override
    {
    }

    void PrintRoutingTable(Ptr<OutputStreamWrapper> stream, Time::Unit unit) const override
    {
    }

    void PrepareOutgoingPacket(Ptr<Packet> packet,
                               Ipv6Header& header,
                               Ptr<Ipv6Route> route) override
    {
        m_prepareOutgoingCalled = true;
    }

    bool m_prepareOutgoingCalled = false; //!< set when PrepareOutgoingPacket() is called
};

/**
 * @ingroup internet-test
 *
 * @brief IPv6 ListRouting negative test.
 */
class Ipv6ListRoutingNegativeTestCase : public TestCase
{
  public:
    Ipv6ListRoutingNegativeTestCase();
    void DoRun() override;
};

Ipv6ListRoutingNegativeTestCase::Ipv6ListRoutingNegativeTestCase()
    : TestCase("Check negative priorities")
{
}

void
Ipv6ListRoutingNegativeTestCase::DoRun()
{
    Ptr<Ipv6ListRouting> lr = CreateObject<Ipv6ListRouting>();
    Ptr<Ipv6RoutingProtocol> aRouting = CreateObject<Ipv6ARouting>();
    Ptr<Ipv6RoutingProtocol> bRouting = CreateObject<Ipv6BRouting>();
    // The Ipv6BRouting should be added with higher priority (larger integer value)
    lr->AddRoutingProtocol(aRouting, -10);
    lr->AddRoutingProtocol(bRouting, -5);
    int16_t first = 3;
    uint32_t num = lr->GetNRoutingProtocols();
    NS_TEST_ASSERT_MSG_EQ(num, 2, "100");
    Ptr<Ipv6RoutingProtocol> firstRp = lr->GetRoutingProtocol(0, first);
    NS_TEST_ASSERT_MSG_EQ(-5, first, "101");
    NS_TEST_ASSERT_MSG_EQ(firstRp, bRouting, "102");
}

/**
 * @ingroup internet-test
 *
 * @brief IPv6 ListRouting positive test.
 */
class Ipv6ListRoutingPositiveTestCase : public TestCase
{
  public:
    Ipv6ListRoutingPositiveTestCase();
    void DoRun() override;
};

Ipv6ListRoutingPositiveTestCase::Ipv6ListRoutingPositiveTestCase()
    : TestCase("Check positive priorities")
{
}

void
Ipv6ListRoutingPositiveTestCase::DoRun()
{
    Ptr<Ipv6ListRouting> lr = CreateObject<Ipv6ListRouting>();
    Ptr<Ipv6RoutingProtocol> aRouting = CreateObject<Ipv6ARouting>();
    Ptr<Ipv6RoutingProtocol> bRouting = CreateObject<Ipv6BRouting>();
    // The Ipv6ARouting should be added with higher priority (larger integer
    // value) and will be fetched first below
    lr->AddRoutingProtocol(aRouting, 10);
    lr->AddRoutingProtocol(bRouting, 5);
    int16_t first = 3;
    int16_t second = 3;
    uint32_t num = lr->GetNRoutingProtocols();
    NS_TEST_ASSERT_MSG_EQ(num, 2, "200");
    Ptr<Ipv6RoutingProtocol> firstRp = lr->GetRoutingProtocol(0, first);
    NS_TEST_ASSERT_MSG_EQ(10, first, "201");
    NS_TEST_ASSERT_MSG_EQ(firstRp, aRouting, "202");
    Ptr<Ipv6RoutingProtocol> secondRp = lr->GetRoutingProtocol(1, second);
    NS_TEST_ASSERT_MSG_EQ(5, second, "203");
    NS_TEST_ASSERT_MSG_EQ(secondRp, bRouting, "204");
}

/**
 * @ingroup internet-test
 *
 * @brief Check that Ipv6ListRouting forwards PrepareOutgoingPacket() to its
 *        member protocols.
 */
class Ipv6ListRoutingPrepareOutgoingPacketTestCase : public TestCase
{
  public:
    Ipv6ListRoutingPrepareOutgoingPacketTestCase();
    void DoRun() override;
};

Ipv6ListRoutingPrepareOutgoingPacketTestCase::Ipv6ListRoutingPrepareOutgoingPacketTestCase()
    : TestCase("Check PrepareOutgoingPacket is forwarded to member protocols")
{
}

void
Ipv6ListRoutingPrepareOutgoingPacketTestCase::DoRun()
{
    Ptr<Ipv6ListRouting> lr = CreateObject<Ipv6ListRouting>();
    Ptr<Ipv6ARouting> aRouting = CreateObject<Ipv6ARouting>();
    Ptr<Ipv6BRouting> bRouting = CreateObject<Ipv6BRouting>();
    lr->AddRoutingProtocol(aRouting, 10);
    lr->AddRoutingProtocol(bRouting, 5);

    Ptr<Packet> packet = Create<Packet>();
    Ipv6Header header;
    Ptr<Ipv6Route> route = Create<Ipv6Route>();
    lr->PrepareOutgoingPacket(packet, header, route);

    // The hook must reach every member; before the forwarding override was
    // added it fell back to the base-class no-op and neither was called.
    NS_TEST_ASSERT_MSG_EQ(aRouting->m_prepareOutgoingCalled,
                          true,
                          "PrepareOutgoingPacket not forwarded to member A");
    NS_TEST_ASSERT_MSG_EQ(bRouting->m_prepareOutgoingCalled,
                          true,
                          "PrepareOutgoingPacket not forwarded to member B");
}

/**
 * @ingroup internet-test
 *
 * @brief IPv6 ListRouting TestSuite
 */
class Ipv6ListRoutingTestSuite : public TestSuite
{
  public:
    Ipv6ListRoutingTestSuite()
        : TestSuite("ipv6-list-routing", Type::UNIT)
    {
        AddTestCase(new Ipv6ListRoutingPositiveTestCase(), TestCase::Duration::QUICK);
        AddTestCase(new Ipv6ListRoutingNegativeTestCase(), TestCase::Duration::QUICK);
        AddTestCase(new Ipv6ListRoutingPrepareOutgoingPacketTestCase(),
                    TestCase::Duration::QUICK);
    }
};

static Ipv6ListRoutingTestSuite
    g_ipv6ListRoutingTestSuite; //!< Static variable for test initialization

} // namespace ns3
