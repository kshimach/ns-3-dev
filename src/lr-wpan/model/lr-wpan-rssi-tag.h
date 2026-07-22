/*
 * Copyright (c) 2026 ns-3 project
 *
 * SPDX-License-Identifier: GPL-2.0-only
 */
#ifndef LR_WPAN_RSSI_TAG_H
#define LR_WPAN_RSSI_TAG_H

#include "ns3/tag.h"

namespace ns3
{
namespace lrwpan
{

/**
 * @ingroup lr-wpan
 * Represent the RSSI (Received Signal Strength Indicator).
 *
 * The RSSI Tag is added to each received packet, and can be
 * used by upper layers to estimate the channel conditions.
 *
 * The RSSI is the total received signal power, in dBm, measured over the
 * preamble of the packet (see LrWpanPhy::EndPreamble()).
 */
class LrWpanRssiTag : public Tag
{
  public:
    /**
     * Get the type ID.
     *
     * @return the object TypeId
     */
    static TypeId GetTypeId();

    TypeId GetInstanceTypeId() const override;

    /**
     * Create a LrWpanRssiTag with the default RSSI of 0 dBm.
     */
    LrWpanRssiTag();

    /**
     * Create a LrWpanRssiTag with the given RSSI value.
     * @param rssi The RSSI, in dBm.
     */
    LrWpanRssiTag(int8_t rssi);

    uint32_t GetSerializedSize() const override;
    void Serialize(TagBuffer i) const override;
    void Deserialize(TagBuffer i) override;
    void Print(std::ostream& os) const override;

    /**
     * Set the RSSI to the given value.
     *
     * @param rssi the value of the RSSI to set, in dBm
     */
    void Set(int8_t rssi);

    /**
     * Get the RSSI value.
     *
     * @return the RSSI value, in dBm
     */
    int8_t Get() const;

  private:
    /**
     * The current RSSI value of the tag, in dBm.
     */
    int8_t m_rssi;
};

} // namespace lrwpan
} // namespace ns3
#endif /* LR_WPAN_RSSI_TAG_H */
