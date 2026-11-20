from dify_plugin import DifyPluginEnv, Plugin

# Exhaustive research is documented at under 300 seconds. Leave headroom for that read.
plugin = Plugin(DifyPluginEnv(MAX_REQUEST_TIMEOUT=360))

if __name__ == "__main__":
    plugin.run()
