export interface ConfigManagement {
  config_key: string
  config_value: string
  description?: string
  is_masked?: boolean
  created_at?: string
  updated_at?: string
}

export interface ConfigManagementUpdate {
  config_value?: string
  description?: string
}
