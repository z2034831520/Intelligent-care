from setuptools import setup

package_name = "smart_care_bridge"

setup(
    name=package_name,
    version="0.1.0",
    packages=[package_name],
    data_files=[
        ("share/ament_index/resource_index/packages", [f"resource/{package_name}"]),
        (f"share/{package_name}", ["package.xml"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="student",
    maintainer_email="student@example.com",
    description="Bridge official RDK ROS2 body detection results to Feishu webhook alerts.",
    license="MIT",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "person_event_bridge = smart_care_bridge.person_event_bridge:main",
            "record_buffer_service = smart_care_bridge.record_buffer_service:main",
            "evidence_file_server = smart_care_bridge.evidence_file_server:main",
            "patrol_gateway = smart_care_bridge.patrol_gateway:main",
            "patrol_once = smart_care_bridge.patrol_once:main",
            "manual_patrol_once = smart_care_bridge.manual_patrol_once:main",
            "openclaw_patrol_command = smart_care_bridge.openclaw_patrol_command:main",
            "openclaw_patrol_worker = smart_care_bridge.openclaw_patrol_worker:main",
            "openclaw_patrol_session_bridge = smart_care_bridge.openclaw_patrol_session_bridge:main",
            "daily_report_once = smart_care_bridge.daily_report_once:main",
        ],
    },
)
