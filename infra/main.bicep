param webAppName string = 'my-app'
param location string = 'westeurope'
param appServicePlanName string = 'my-app-plan'
param skuName string = 'B1'
param skuTier string = 'Basic'
param linuxFxVersion string = 'NODE|18-lts'
param environment string = 'Development'
param logLevel string = 'Information'
param port string = '8080'

resource plan 'Microsoft.Web/serverfarms@2022-03-01' = {
  name: appServicePlanName
  location: location
  sku: {
    name: skuName
    tier: skuTier
  }
  properties: {
    reserved: true
  }
}

resource web 'Microsoft.Web/sites@2022-03-01' = {
  name: webAppName
  location: location
  kind: 'app,linux'
  properties: {
    serverFarmId: plan.id
    siteConfig: {
      linuxFxVersion: linuxFxVersion
      appSettings: [
        {
          name: 'APP_ENV'
          value: environment
        }
        {
          name: 'LOG_LEVEL'
          value: logLevel
        }
        {
          name: 'PORT'
          value: port
        }
      ]
    }
  }
}

output webAppDefaultHostName string = web.properties.defaultHostName
