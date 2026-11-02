"""Shared application and distribution version."""
appVersion = "0.2.0"
releaseStage = "alpha"
version = f"{appVersion}-{releaseStage}" if releaseStage else appVersion
displayVersion = f"{releaseStage.capitalize()} {appVersion}" if releaseStage else appVersion
