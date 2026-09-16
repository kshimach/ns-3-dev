/*
 * Copyright (c) 2026 ns-3 RPL module contributors
 *
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * Replicates the conditions of:
 *   E. Baccelli, M. Philipp, M. Goyal, "The P2P-RPL Routing Protocol for
 *   IPv6 Sensor Networks: Testbed Experiments," SoftCOM 2011.
 * and evaluates AODV-RPL (RFC 9854, which postdates that paper) under the
 * same conditions, extending the comparison the paper never made.
 *
 * Matched conditions (paper section 4.1/4.2):
 *   - 27 nodes, IEEE 802.15.4-class radio, one root/sink.
 *   - Resulting network graph average node degree 4.39 (paper Fig. 5) --
 *     since the paper's raw physical layout (a 5x5m/60cm-pitch indoor
 *     testbed at 2.4GHz) is not a meaningful physical target for our
 *     synthetic 802.15.4-class UDGM model, this replication instead
 *     calibrates deployment area/commRange to reproduce that reported
 *     *graph* invariant (Monte Carlo calibration: 192m x 192m square,
 *     commRange=50m, N=27 -> avg degree ~4.38), which is what actually
 *     drives RPL's DODAG-depth-dependent behaviour.
 *   - Real observed Trickle Imin=4096ms (paper section 5: "Contiki uses a
 *     value of 4096 ms for the minimum DIO interval instead of 8 ms as
 *     recommended by the specification") -- NOT contrib/rpl's own module
 *     defaults (P2P-RPL 64ms / AODV-RPL 128ms), and not RFC 6997's 8ms.
 *   - Random (source, target) pairs, one discovery per pair, no repeat
 *     traffic beyond the discovery itself (paper section 4.2).
 *
 * Metrics replicated against the paper's own headline figures (section
 * 4.2, Fig. 7/8, and the unnumbered paragraph on request/reply asymmetry):
 *   - Route length: discovered hop count vs "plain RPL" non-storing via-root
 *     baseline (depth(src)+depth(dst)). Paper: ~3 hops median vs ~5.
 *   - Fraction of discovered routes NOT traversing the root.
 *     Paper: 16.03% (P2P-RPL) vs 74.53% (RPL storing mode).
 *   - Discovery round-trip latency (request out -> reply back at Origin).
 *     Paper: 8.43s average.
 *   - Request-reached-target rate vs full-round-trip (reply-back) rate --
 *     the paper's open reliability gap (99.16% vs 57.87%), using the new
 *     DiscoveryTargetReached trace source (contrib/rpl) to separate the
 *     two halves of a discovery attempt, which this paper's own testbed
 *     could not do without instrumenting the firmware itself.
 *
 * AODV-RPL did not exist in 2011 (RFC 9854 postdates RFC 6997); it is
 * evaluated here under the identical conditions as an extension of the
 * paper's comparison, not a replication of anything the paper itself did.
 */

#include "ns3/applications-module.h"
#include "ns3/core-module.h"
#include "ns3/internet-module.h"
#include "ns3/mobility-module.h"
#include "ns3/network-module.h"
#include "ns3/rpl-module.h"

#include <fstream>
#include <iostream>
#include <map>
#include <set>
#include <vector>

using namespace ns3;

NS_LOG_COMPONENT_DEFINE("P2pRplPaperReplication");

constexpr int64_t kTopologyStream = 10;
constexpr int64_t kChannelStream = 30;
constexpr int64_t kPairSelectionStream = 40;
constexpr int64_t kRplStreamBase = 1000;

/// Same quadratic-loss UDGM model as scratch/rpl-large-scale-system-test.cc
/// (no asymmetry option needed here -- this replication does not touch
/// AODV-RPL's S=0 mode, which is a routing-mode question, not a channel one).
class UdgmChannel : public SimpleChannel
{
  public:
    UdgmChannel()
        : m_rng(CreateObject<UniformRandomVariable>())
    {
        m_rng->SetStream(kChannelStream);
    }

    void SetParameters(double rangeMeters, double edgeSuccessRate)
    {
        m_range = rangeMeters;
        m_edgeSuccessRate = edgeSuccessRate;
    }

    void Send(Ptr<Packet> p,
              uint16_t protocol,
              Mac48Address to,
              Mac48Address from,
              Ptr<SimpleNetDevice> sender) override
    {
        for (std::size_t i = 0; i < GetNDevices(); ++i)
        {
            Ptr<SimpleNetDevice> receiver = DynamicCast<SimpleNetDevice>(GetDevice(i));
            if (!receiver || receiver == sender)
            {
                continue;
            }
            Ptr<MobilityModel> txMobility = sender->GetNode()->GetObject<MobilityModel>();
            Ptr<MobilityModel> rxMobility = receiver->GetNode()->GetObject<MobilityModel>();
            double distance = txMobility->GetDistanceFrom(rxMobility);
            if (distance > m_range)
            {
                continue;
            }
            double edgeFraction = (m_range > 0.0) ? (distance / m_range) : 0.0;
            double deliveryProbability =
                1.0 - (1.0 - m_edgeSuccessRate) * edgeFraction * edgeFraction;
            if (m_rng->GetValue(0.0, 1.0) > deliveryProbability)
            {
                continue;
            }
            Simulator::ScheduleWithContext(receiver->GetNode()->GetId(),
                                           Seconds(0),
                                           &SimpleNetDevice::Receive,
                                           receiver,
                                           p->Copy(),
                                           protocol,
                                           to,
                                           from);
        }
    }

  private:
    double m_range{50.0};
    double m_edgeSuccessRate{0.9};
    Ptr<UniformRandomVariable> m_rng;
};

static NodeContainer g_nodes;
static std::vector<bool> g_lastJoined;
static std::vector<uint16_t> g_lastRank;
static double g_lastChangeTime = 0.0;

static void
CheckConvergence(double windowEnd)
{
    bool changed = false;
    for (uint32_t i = 0; i < g_nodes.GetN(); ++i)
    {
        Ptr<rpl::RplRoutingProtocol> rpl = g_nodes.Get(i)->GetObject<rpl::RplRoutingProtocol>();
        bool joined = rpl->IsJoined();
        uint16_t rank = rpl->GetRank();
        if (joined != g_lastJoined[i] || rank != g_lastRank[i])
        {
            changed = true;
            g_lastJoined[i] = joined;
            g_lastRank[i] = rank;
        }
    }
    if (changed)
    {
        g_lastChangeTime = Simulator::Now().GetSeconds();
    }
    if (Simulator::Now().GetSeconds() < windowEnd)
    {
        Simulator::Schedule(MilliSeconds(200), &CheckConvergence, windowEnd);
    }
}

/// Hop depth to Root via each node's preferred-parent chain -- this IS the
/// "plain RPL" non-storing-mode via-root path length the paper's own
/// baseline used (section 4.2: "a global DAG was used to establish upward
/// routes and the DAO mechanism in non-storing mode ... the path through
/// the sink was thus recorded").
static std::map<uint32_t, uint32_t>
ComputeDepths()
{
    std::map<uint32_t, uint32_t> depth;
    std::map<Ipv6Address, uint32_t> addrToIdx;
    for (uint32_t i = 0; i < g_nodes.GetN(); ++i)
    {
        Ptr<rpl::RplRoutingProtocol> rpl = g_nodes.Get(i)->GetObject<rpl::RplRoutingProtocol>();
        if (rpl->IsJoined())
        {
            Ipv6Address linkLocal =
                g_nodes.Get(i)->GetObject<Ipv6L3Protocol>()->GetAddress(1, 0).GetAddress();
            addrToIdx[linkLocal] = i;
        }
    }
    depth[0] = 0;
    for (uint32_t i = 1; i < g_nodes.GetN(); ++i)
    {
        Ptr<rpl::RplRoutingProtocol> rpl = g_nodes.Get(i)->GetObject<rpl::RplRoutingProtocol>();
        if (!rpl->IsJoined())
        {
            continue;
        }
        std::set<uint32_t> visited;
        uint32_t cur = i;
        uint32_t d = 0;
        while (cur != 0 && d <= g_nodes.GetN())
        {
            if (visited.count(cur))
            {
                d = 0; // loop -- report as unresolved rather than a bogus depth
                break;
            }
            visited.insert(cur);
            Ptr<rpl::RplRoutingProtocol> curRpl =
                g_nodes.Get(cur)->GetObject<rpl::RplRoutingProtocol>();
            auto it = addrToIdx.find(curRpl->GetPreferredParent());
            if (it == addrToIdx.end())
            {
                d = 0;
                break;
            }
            cur = it->second;
            d++;
        }
        depth[i] = d;
    }
    return depth;
}

/// One (source, target) discovery trial's outcome.
struct TrialResult
{
    uint32_t srcIdx;
    uint32_t dstIdx;
    int32_t bothJoined = -1;        // 1/0, filled at trigger time; -1 = never reached trigger time
    double requestReachedMs = -1.0; // -1 = request never reached target
    double roundTripMs = -1.0;      // -1 = reply never made it back
    int32_t hopCount = -1;          // discovered path length; -1 if not H=0 or not found
    int32_t throughRoot = -1;       // 1/0 if H=0 and found, else -1 (unknown)
};
static std::vector<TrialResult> g_results;

/// Pending discoveries keyed by the Origin's own global address (== the
/// temporary DODAG's DODAGID per RFC 6997/9854), so the DiscoveryTargetReached
/// trace (fired on the TARGET node, which does not otherwise know which of
/// our TrialResult entries it belongs to) can be matched back to a trial.
static std::map<Ipv6Address, std::pair<uint32_t, Time>> g_pendingByOriginAddr; // -> (resultIdx, triggerTime)

static void
OnDiscoveryTargetReached(std::string context, uint8_t instanceId, Ipv6Address dodagId)
{
    (void)context;
    (void)instanceId;
    auto it = g_pendingByOriginAddr.find(dodagId);
    if (it == g_pendingByOriginAddr.end())
    {
        return;
    }
    TrialResult& r = g_results[it->second.first];
    if (r.requestReachedMs < 0.0)
    {
        r.requestReachedMs = (Simulator::Now() - it->second.second).GetMilliSeconds();
    }
}

static void
PollTrial(uint32_t resultIdx,
         Ipv6Address target,
         std::string protocol,
         bool hopByHop,
         Time triggerTime,
         Time deadline)
{
    TrialResult& r = g_results[resultIdx];
    Ptr<rpl::RplRoutingProtocol> rpl = g_nodes.Get(r.srcIdx)->GetObject<rpl::RplRoutingProtocol>();
    bool found = false;
    std::vector<Ipv6Address> hops;
    if (hopByHop)
    {
        Ipv6Address nextHop;
        uint8_t instId;
        found = rpl->GetHopByHopRoute(target, nextHop, instId);
    }
    else if (protocol == "p2prpl")
    {
        found = rpl->GetP2pRoute(target, hops);
    }
    else
    {
        found = rpl->GetAodvRoute(target, hops);
    }
    if (found)
    {
        if (r.roundTripMs < 0.0)
        {
            r.roundTripMs = (Simulator::Now() - triggerTime).GetMilliSeconds();
            if (!hopByHop)
            {
                r.hopCount = static_cast<int32_t>(hops.size());
                Ipv6Address rootAddr =
                    g_nodes.Get(0)->GetObject<rpl::RplRoutingProtocol>()->GetGlobalAddress();
                r.throughRoot = 0;
                for (const auto& h : hops)
                {
                    if (h == rootAddr)
                    {
                        r.throughRoot = 1;
                        break;
                    }
                }
            }
        }
        return;
    }
    if (Simulator::Now() >= deadline)
    {
        return; // leaves roundTripMs/hopCount/throughRoot at their -1 "never" defaults
    }
    Simulator::Schedule(MilliSeconds(50),
                        &PollTrial,
                        resultIdx,
                        target,
                        protocol,
                        hopByHop,
                        triggerTime,
                        deadline);
}

int
main(int argc, char** argv)
{
    uint32_t nNodes = 27;         // paper section 4.1
    double areaSide = 192.0;      // Monte Carlo-calibrated for avg degree ~4.39 (see file header)
    double commRange = 50.0;
    double edgeSuccessRate = 0.9; // paper's real testbed loss is not a synthetic rate we can copy;
                                  // 0.9 is a mild-loss condition disclosed as an approximation
    std::string protocol = "p2prpl"; // "p2prpl" or "aodvrpl"
    bool hopByHop = false;           // false = H=0/source-routed, matching the paper's own
                                     // non-storing-mode methodology (needed for hop-count/
                                     // root-traversal instrumentation; see PollTrial)
    bool p2pDroAckRequested = true;  // true = contrib/rpl's improved default; false = as
                                     // literally specified in RFC 6997 / evaluated by the paper
    uint32_t reactiveDioIntervalMinMs = 4096; // paper section 5: Contiki's real observed Imin
    uint32_t nTrials = 230;                   // paper section 4.2: "repeated 230 times"
    // At Imin=4096ms, per-hop relay latency is gated by each relay's own
    // Trickle window, so multi-hop discovery can take well past the paper's
    // own 8.43s *average* (that average was measured on the paper's own
    // specific fixed hop distances, not a bound) -- a smoke test at 15s
    // truncated genuine late completions (request-reached traces firing
    // past the poll deadline). 90s spacing / 75s poll budget is generous
    // enough that a trial's own temporary DODAG has fully expired before
    // the next trial starts, avoiding any cross-trial interference.
    double trialSpacingS = 90.0;
    double pollDeadlineS = 75.0;
    double settleTime = 60.0;
    std::string csvPath = "p2p-rpl-paper-replication.csv";
    bool verbose = false;

    CommandLine cmd(__FILE__);
    cmd.AddValue("nNodes", "Number of nodes (paper: 27)", nNodes);
    cmd.AddValue("areaSide", "Square deployment side length in meters", areaSide);
    cmd.AddValue("commRange", "UDGM communication range in meters", commRange);
    cmd.AddValue("edgeSuccessRate", "Delivery probability at edge of commRange", edgeSuccessRate);
    cmd.AddValue("protocol", "p2prpl or aodvrpl", protocol);
    cmd.AddValue("hopByHop", "true=H=1, false=H=0 (source-routed; needed for hop/root metrics)",
                 hopByHop);
    cmd.AddValue("p2pDroAckRequested", "P2P-DRO-ACK: true=contrib/rpl default, false=RFC 6997 as-is",
                 p2pDroAckRequested);
    cmd.AddValue("reactiveDioIntervalMinMs", "Reactive discovery Trickle Imin in ms (paper: 4096)",
                 reactiveDioIntervalMinMs);
    cmd.AddValue("nTrials", "Number of (source,target) discovery trials (paper: 230)", nTrials);
    cmd.AddValue("trialSpacingS", "Seconds between successive trials", trialSpacingS);
    cmd.AddValue("pollDeadlineS", "Seconds to wait for a trial to complete before giving up",
                 pollDeadlineS);
    cmd.AddValue("settleTime", "Time to let the base DODAG converge before trials start (s)",
                 settleTime);
    cmd.AddValue("csv", "CSV output path", csvPath);
    cmd.AddValue("verbose", "Enable verbose RPL logging", verbose);
    cmd.Parse(argc, argv);

    if (verbose)
    {
        LogComponentEnable("RplRoutingProtocol",
                           LogLevel(LOG_LEVEL_INFO | LOG_PREFIX_TIME | LOG_PREFIX_NODE));
    }

    g_nodes.Create(nNodes);

    MobilityHelper mobility;
    Ptr<ListPositionAllocator> positions = CreateObject<ListPositionAllocator>();
    positions->Add(Vector(areaSide / 2.0, areaSide / 2.0, 0.0)); // root, unprivileged position
    Ptr<UniformRandomVariable> urv = CreateObject<UniformRandomVariable>();
    urv->SetStream(kTopologyStream);
    urv->SetAttribute("Min", DoubleValue(0.0));
    urv->SetAttribute("Max", DoubleValue(areaSide));
    for (uint32_t i = 1; i < nNodes; ++i)
    {
        positions->Add(Vector(urv->GetValue(), urv->GetValue(), 0.0));
    }
    mobility.SetPositionAllocator(positions);
    mobility.SetMobilityModel("ns3::ConstantPositionMobilityModel");
    mobility.Install(g_nodes);

    Ptr<UdgmChannel> channel = CreateObject<UdgmChannel>();
    channel->SetParameters(commRange, edgeSuccessRate);
    NetDeviceContainer devices;
    for (uint32_t i = 0; i < nNodes; ++i)
    {
        Ptr<SimpleNetDevice> dev = CreateObject<SimpleNetDevice>();
        dev->SetAddress(Mac48Address::Allocate());
        g_nodes.Get(i)->AddDevice(dev);
        dev->SetChannel(channel);
        devices.Add(dev);
    }

    RplHelper rplHelper;
    rplHelper.Set("Mop", UintegerValue(rpl::RPL_MOP_STORING_NO_MULTICAST));
    // Base-RPL Trickle: not specified by the paper for its own DODAG
    // formation, so contrib/rpl's own module default is used unmodified.
    rplHelper.Set("P2pDioIntervalMin", TimeValue(MilliSeconds(reactiveDioIntervalMinMs)));
    rplHelper.Set("AodvDioIntervalMin", TimeValue(MilliSeconds(reactiveDioIntervalMinMs)));
    rplHelper.Set("P2pDroAckRequested", BooleanValue(p2pDroAckRequested));

    InternetStackHelper internetv6;
    internetv6.SetIpv4StackInstall(false);
    internetv6.SetRoutingHelper(rplHelper);
    internetv6.Install(g_nodes);
    rplHelper.AssignStreams(g_nodes, kRplStreamBase);

    Ipv6AddressHelper ipv6;
    Ipv6InterfaceContainer interfaces = ipv6.AssignWithoutAddress(devices);
    for (uint32_t i = 0; i < nNodes; ++i)
    {
        interfaces.SetForwarding(i, true);
    }
    rplHelper.SetRoot(g_nodes.Get(0), Ipv6Address("2001:1::"), 64);

    Config::Connect("/NodeList/*/$ns3::rpl::RplRoutingProtocol/DiscoveryTargetReached",
                    MakeCallback(&OnDiscoveryTargetReached));

    g_lastJoined.assign(nNodes, false);
    g_lastRank.assign(nNodes, 0);
    Simulator::Schedule(MilliSeconds(200), &CheckConvergence, settleTime);

    // Random (source, target) pairs, both != root, src != dst -- paper
    // section 4.2: "random pairs of nodes were successively chosen".
    Ptr<UniformRandomVariable> pairRng = CreateObject<UniformRandomVariable>();
    pairRng->SetStream(kPairSelectionStream);
    g_results.reserve(nTrials);
    for (uint32_t t = 0; t < nTrials; ++t)
    {
        uint32_t src = 1 + static_cast<uint32_t>(pairRng->GetInteger(0, nNodes - 2));
        uint32_t dst;
        do
        {
            dst = 1 + static_cast<uint32_t>(pairRng->GetInteger(0, nNodes - 2));
        } while (dst == src);

        double triggerAt = settleTime + 5.0 + t * trialSpacingS;
        g_results.push_back(TrialResult{src, dst});
        uint32_t resultIdx = static_cast<uint32_t>(g_results.size() - 1);

        Simulator::Schedule(Seconds(triggerAt),
                           [resultIdx, src, dst, protocol, hopByHop, pollDeadlineS]() {
            Ptr<rpl::RplRoutingProtocol> srcRpl =
                g_nodes.Get(src)->GetObject<rpl::RplRoutingProtocol>();
            Ptr<rpl::RplRoutingProtocol> dstRpl =
                g_nodes.Get(dst)->GetObject<rpl::RplRoutingProtocol>();
            g_results[resultIdx].bothJoined = (srcRpl->IsJoined() && dstRpl->IsJoined()) ? 1 : 0;
            if (!g_results[resultIdx].bothJoined)
            {
                return; // leave this trial's other fields at their "never" defaults
            }
            Ipv6Address target = dstRpl->GetGlobalAddress();
            Ipv6Address origin = srcRpl->GetGlobalAddress();
            Time triggerTime = Simulator::Now();
            g_pendingByOriginAddr[origin] = {resultIdx, triggerTime};
            if (protocol == "p2prpl")
            {
                srcRpl->DiscoverP2pRoute(target, hopByHop);
            }
            else
            {
                srcRpl->DiscoverRoute(target, hopByHop);
            }
            Simulator::Schedule(MilliSeconds(50),
                                &PollTrial,
                                resultIdx,
                                target,
                                protocol,
                                hopByHop,
                                triggerTime,
                                triggerTime + Seconds(pollDeadlineS));
        });
    }

    double simTime = settleTime + 5.0 + nTrials * trialSpacingS + 20.0;
    Simulator::Stop(Seconds(simTime));
    Simulator::Run();

    std::map<uint32_t, uint32_t> depth = ComputeDepths();
    uint32_t joinedCount = 0;
    for (uint32_t i = 0; i < nNodes; ++i)
    {
        if (g_nodes.Get(i)->GetObject<rpl::RplRoutingProtocol>()->IsJoined())
        {
            joinedCount++;
        }
    }

    std::cout << "\n================ [P2P-RPL Paper Replication] ================\n"
              << " Protocol:                " << protocol << " (P2pDroAckRequested="
              << (p2pDroAckRequested ? "true" : "false") << ", hopByHop="
              << (hopByHop ? "true" : "false") << ")\n"
              << " Nodes joined:            " << joinedCount << "/" << nNodes << "\n"
              << " Convergence time:        " << g_lastChangeTime << " s\n"
              << "===============================================================\n";

    bool writeHeader = false;
    {
        std::ifstream probe(csvPath);
        writeHeader = !probe.good();
    }
    std::ofstream csv(csvPath, std::ios::app);
    if (writeHeader)
    {
        csv << "protocol,p2pDroAckRequested,hopByHop,rngRun,nNodes,areaSide,commRange,"
               "edgeSuccessRate,reactiveDioIntervalMinMs,joinedCount,srcIdx,dstIdx,bothJoined,"
               "requestReachedMs,roundTripMs,hopCount,throughRoot,baselineDoglegHops\n";
    }
    for (auto& r : g_results)
    {
        uint32_t baseline = 0;
        auto sIt = depth.find(r.srcIdx);
        auto dIt = depth.find(r.dstIdx);
        if (sIt != depth.end() && dIt != depth.end())
        {
            baseline = sIt->second + dIt->second;
        }
        csv << protocol << "," << (p2pDroAckRequested ? 1 : 0) << "," << (hopByHop ? 1 : 0) << ","
            << RngSeedManager::GetRun() << "," << nNodes << "," << areaSide << "," << commRange
            << "," << edgeSuccessRate << "," << reactiveDioIntervalMinMs << "," << joinedCount
            << "," << r.srcIdx << "," << r.dstIdx << "," << r.bothJoined << ","
            << r.requestReachedMs << ","
            << r.roundTripMs << "," << r.hopCount << "," << r.throughRoot << "," << baseline
            << "\n";
    }
    csv.close();

    Simulator::Destroy();
    return 0;
}
