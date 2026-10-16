export type AssetModelPoint = {
  spot: number;
  strike: number;
  tau: number;
  rate: number;
  yield_: number;
  parameters: {
    diffusion_vol: number;
    v0: number;
    theta: number;
    intensity: number;
    jump_mean: number;
    jump_std: number;
    vol_of_vol: number;
    rho: number;
    kappa: number;
  };
};
