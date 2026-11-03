{
  description = "Cinemana Stremio add-on";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs }:
    let
      systems = [
        "aarch64-darwin"
        "aarch64-linux"
        "x86_64-linux"
      ];

      forAllSystems = nixpkgs.lib.genAttrs systems;

      pythonFor = pkgs:
        pkgs.python312.withPackages (ps:
          with ps; [
            flask
            flask-cors
            gunicorn
            requests
          ]);
    in
    {
      packages = forAllSystems (system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
        in
        {
          default = pkgs.writeShellApplication {
            name = "cinemana-stremio";
            runtimeInputs = [ (pythonFor pkgs) ];
            text = ''
              exec python ${./addon.py}
            '';
          };
        });

      apps = forAllSystems (system: {
        default = {
          type = "app";
          program = "${self.packages.${system}.default}/bin/cinemana-stremio";
          meta.description = "Cinemana Stremio add-on";
        };
      });

      devShells = forAllSystems (system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
        in
        {
          default = pkgs.mkShell {
            packages = [ (pythonFor pkgs) ];
          };
        });
    };
}
