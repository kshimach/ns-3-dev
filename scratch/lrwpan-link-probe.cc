/*
 * Copyright (c) 2026 ns-3 RPL module contributors
 *
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * Calibration probe for rpl-large-scale-system-test --link=lrwpan: two
 * lr-wpan nodes d metres apart, node 0 sends N frames to node 1, and the
 * program prints how many arrive. Uses the harness's exact LogDistance
 * parameterisation (mean rx power at --rangeM = sensitivity + --marginDb),
 * so the tables it prints say what --lrMarginDb / distance actually mean
 * for one frame, with nothing else (no routing, no other traffic) on the air.
 *
 *   broadcast: one shot, no ACK  -> raw per-frame delivery probability
 *   unicast:   ACK + macMaxFrameRetries -> what the MAC delivers after retries
 */

#include "ns3/core-module.h"
#include "ns3/lr-wpan-module.h"
#include "ns3/mobility-module.h"
#include "ns3/network-module.h"
#include "ns3/propagation-module.h"
#include "ns3/spectrum-module.h"

#include <cmath>
#include <iostream>

using namespace ns3;
using namespace ns3::lrwpan;

static uint32_t g_rx = 0;
static uint32_t g_confirmOk = 0;
static uint32_t g_confirmFail = 0;

static void
Rx(McpsDataIndicationParams, Ptr<Packet>)
{
    g_rx++;
}

static void
Confirm(McpsDataConfirmParams p)
{
    if (p.m_status == MacStatus::SUCCESS)
    {
        g_confirmOk++;
    }
    else
    {
        g_confirmFail++;
    }
}

int
main(int argc, char** argv)
{
    double distance = 38.0;
    double marginDb = 0.0;
    double rangeM = 50.0;
    double exponent = 3.0;
    double asymDb = 0.0; // extra loss for the 1 -> 0 direction only (node 1 -> node 0)
    uint32_t frameBytes = 80;
    uint32_t nFrames = 1000;
    bool unicast = false;

    CommandLine cmd(__FILE__);
    cmd.AddValue("distance", "node separation (m)", distance);
    cmd.AddValue("marginDb", "rx power above sensitivity at rangeM (dB)", marginDb);
    cmd.AddValue("rangeM", "distance at which margin is defined (m)", rangeM);
    cmd.AddValue("exponent", "LogDistance exponent", exponent);
    cmd.AddValue("frameBytes", "MSDU size in bytes", frameBytes);
    cmd.AddValue("nFrames", "frames to send", nFrames);
    cmd.AddValue("unicast", "true: unicast with ACK/retries; false: broadcast, no ACK", unicast);
    cmd.Parse(argc, argv);

    NodeContainer nodes;
    nodes.Create(2);
    MobilityHelper mobility;
    Ptr<ListPositionAllocator> pos = CreateObject<ListPositionAllocator>();
    pos->Add(Vector(0, 0, 0));
    pos->Add(Vector(distance, 0, 0));
    mobility.SetPositionAllocator(pos);
    mobility.SetMobilityModel("ns3::ConstantPositionMobilityModel");
    mobility.Install(nodes);

    constexpr double kTxPowerDbm = 0.0;
    constexpr double kSensitivityDbm = -106.58;
    double refLossDb = kTxPowerDbm - (kSensitivityDbm + marginDb) - 10.0 * exponent * std::log10(rangeM);

    LrWpanHelper helper;
    helper.SetPropagationDelayModel("ns3::ConstantSpeedPropagationDelayModel");
    helper.AddPropagationLossModel("ns3::LogDistancePropagationLossModel",
                                   "Exponent",
                                   DoubleValue(exponent),
                                   "ReferenceDistance",
                                   DoubleValue(1.0),
                                   "ReferenceLoss",
                                   DoubleValue(refLossDb));
    NetDeviceContainer devs = helper.Install(nodes);
    helper.AssignStreams(devs, 100);
    helper.CreateAssociatedPan(devs, 1);
    Ptr<LrWpanErrorModel> em = CreateObject<LrWpanErrorModel>();
    Ptr<LrWpanNetDevice> d0 = DynamicCast<LrWpanNetDevice>(devs.Get(0));
    Ptr<LrWpanNetDevice> d1 = DynamicCast<LrWpanNetDevice>(devs.Get(1));
    d0->GetPhy()->SetErrorModel(em);
    d1->GetPhy()->SetErrorModel(em);
    d1->GetMac()->SetMcpsDataIndicationCallback(MakeCallback(&Rx));
    d0->GetMac()->SetMcpsDataConfirmCallback(MakeCallback(&Confirm));

    Mac16Address dst = unicast ? d1->GetMac()->GetShortAddress() : Mac16Address("ff:ff");
    for (uint32_t i = 0; i < nFrames; ++i)
    {
        Simulator::Schedule(Seconds(1.0 + 0.1 * i), [d0, dst, frameBytes, unicast, i]() {
            McpsDataRequestParams params;
            params.m_srcAddrMode = SHORT_ADDR;
            params.m_dstAddrMode = SHORT_ADDR;
            params.m_dstPanId = 1;
            params.m_dstAddr = dst;
            params.m_msduHandle = static_cast<uint8_t>(i);
            params.m_txOptions = unicast ? TX_OPTION_ACK : 0;
            d0->GetMac()->McpsDataRequest(params, Create<Packet>(frameBytes));
        });
    }
    Simulator::Stop(Seconds(2.0 + 0.1 * nFrames));
    Simulator::Run();
    Simulator::Destroy();

    std::cout << (unicast ? "unicast " : "broadcast ") << "d=" << distance << " margin=" << marginDb
              << " frame=" << frameBytes << "B  delivered=" << g_rx << "/" << nFrames << " ("
              << 100.0 * g_rx / nFrames << "%)";
    if (unicast)
    {
        std::cout << "  macConfirmOk=" << g_confirmOk << " macConfirmFail=" << g_confirmFail;
    }
    std::cout << "\n";
    (void)asymDb;
    return 0;
}
