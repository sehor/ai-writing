"""Retired mixin package (P2-03).

The mixin implementations moved to app.data.repositories, coordinated by
app.data.unit_of_work and app.data.flows. Only the scene-proposal error
shim remains because routers import those symbols from here.
"""
