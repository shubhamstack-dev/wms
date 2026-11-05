import React from 'react'
import { api } from '../api.js'
import { useApp } from '../ctx.jsx'
import { Card, Pill, Table, useLoad } from '../ui.jsx'

export default function Audit() {
  const { whId } = useApp()
  const [rows] = useLoad(() => api.get(`/warehouses/${whId}/audit`), [whId])
  return (
    <Card title="Audit trail" sub="Every movement, configuration change and assignment in this warehouse (latest 300)">
      <Table rows={rows} empty="No entries" cols={[
        { h: 'Time (UTC)', mono: true, r: a => a.ts?.slice(0, 16).replace('T', ' ') }, { h: 'Role', r: a => <Pill>{a.role}</Pill> },
        { h: 'Action', mono: true, r: a => a.action }, { h: 'Detail', r: a => a.detail },
      ]} />
    </Card>
  )
}
