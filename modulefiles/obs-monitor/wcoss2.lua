help([[
Load python virtual environment for obs-monitor
]])

local pkgName    = myModuleName()
local pkgVersion = myModuleVersion()
local pkgNameVer = myModuleFullName()

conflict(pkgName)


load ("python/3.10.4")

local pyenvpath = "/lfs/h2/emc/da/noscrub/edward.safford/python/envs/"
local pyenvname = "obs-mon"

local pyenvactivate = pathJoin(pyenvpath, pyenvname, "bin/activate")

if (mode() == "load") then
  local activate_cmd = "source "..pyenvactivate
  execute{cmd=activate_cmd, modeA={"load"}}
  prepend_path("PATH", "/lfs/h2/emc/da/noscrub/edward.safford/python/envs/obs-mon/bin")
  prepend_path("PYTHONPATH", "/lfs/h2/emc/da/noscrub/edward.safford/python/envs/obs-mon")

else
  if (mode() == "unload") then
    local deactivate_cmd = "deactivate"
    execute{cmd=deactivate_cmd, modeA={"unload"}}
  end
end

whatis("Name: ".. pkgName)
whatis("Version: ".. pkgVersion)
whatis("Category: Obs-monitor")
whatis("Description: Load all libraries needed for obs-monitor")

