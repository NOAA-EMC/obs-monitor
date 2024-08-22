help([[
Load python virtual environment for obs-monitor
]])

local pkgName    = myModuleName()
local pkgVersion = myModuleVersion()
local pkgNameVer = myModuleFullName()

conflict(pkgName)


prepend_path("MODULEPATH", " /work/noaa/epic/role-epic/spack-stack/hercules/spack-stack-1.6.0/envs/unified-env-intel-2023.2.4/install/modulefiles/Core")

load ("stack-intel/2021.10.0")
load ("python/3.10.8")

local pyenvpath = "/work/noaa/da/esafford/noscrub/python/envs/"
local pyenvname = "obs-mon"

local pyenvactivate = pathJoin(pyenvpath, pyenvname, "bin/activate")

if (mode() == "load") then
  local activate_cmd = "source "..pyenvactivate
  execute{cmd=activate_cmd, modeA={"load"}}
  prepend_path("PATH", "/work/noaa/da/esafford/noscrub/python/envs/obs-mon/bin")
  prepend_path("PYTHONPATH", "/work/noaa/da/esafford/noscrub/python/envs/obs-mon")

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

