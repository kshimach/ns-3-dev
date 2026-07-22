/*
 * Copyright (c) 2026 ns-3 project
 *
 * SPDX-License-Identifier: GPL-2.0-only
 */
#include "lr-wpan-rssi-tag.h"

#include "ns3/integer.h"

namespace ns3
{
namespace lrwpan
{

NS_OBJECT_ENSURE_REGISTERED(LrWpanRssiTag);

TypeId
LrWpanRssiTag::GetTypeId()
{
    static TypeId tid = TypeId("ns3::lrwpan::LrWpanRssiTag")
                            .SetParent<Tag>()
                            .SetGroupName("LrWpan")
                            .AddConstructor<LrWpanRssiTag>()
                            .AddAttribute("Rssi",
                                          "The RSSI of the last packet received, in dBm",
                                          IntegerValue(0),
                                          MakeIntegerAccessor(&LrWpanRssiTag::Get),
                                          MakeIntegerChecker<int8_t>());
    return tid;
}

TypeId
LrWpanRssiTag::GetInstanceTypeId() const
{
    return GetTypeId();
}

LrWpanRssiTag::LrWpanRssiTag()
    : m_rssi(0)
{
}

LrWpanRssiTag::LrWpanRssiTag(int8_t rssi)
    : m_rssi(rssi)
{
}

uint32_t
LrWpanRssiTag::GetSerializedSize() const
{
    return sizeof(int8_t);
}

void
LrWpanRssiTag::Serialize(TagBuffer i) const
{
    i.WriteU8(static_cast<uint8_t>(m_rssi));
}

void
LrWpanRssiTag::Deserialize(TagBuffer i)
{
    m_rssi = static_cast<int8_t>(i.ReadU8());
}

void
LrWpanRssiTag::Print(std::ostream& os) const
{
    os << "Rssi = " << +m_rssi << " dBm";
}

void
LrWpanRssiTag::Set(int8_t rssi)
{
    m_rssi = rssi;
}

int8_t
LrWpanRssiTag::Get() const
{
    return m_rssi;
}

} // namespace lrwpan
} // namespace ns3
