from __future__ import annotations

from pathlib import Path

from app.scanner.repo_scanner import scan_repository


def test_repo_scanner_detects_spring_layers(tmp_path: Path) -> None:
    (tmp_path / "src/main/java/com/example/controller").mkdir(parents=True)
    (tmp_path / "src/main/java/com/example/service").mkdir(parents=True)
    (tmp_path / "src/main/java/com/example/repository").mkdir(parents=True)
    (tmp_path / "src/test/java/com/example").mkdir(parents=True)

    (tmp_path / "pom.xml").write_text(
        """
<project>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>2.1.18.RELEASE</version>
  </parent>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
  </dependencies>
</project>
""",
        encoding="utf-8",
    )
    (tmp_path / "src/main/java/com/example/LegacyApplication.java").write_text(
        "@SpringBootApplication class LegacyApplication {}", encoding="utf-8"
    )
    (tmp_path / "src/main/java/com/example/controller/OrderController.java").write_text(
        '@RestController @RequestMapping("/orders") class OrderController { @GetMapping("/{id}") String get() { return ""; } }',
        encoding="utf-8",
    )
    (tmp_path / "src/main/java/com/example/service/OrderService.java").write_text(
        "@Service class OrderService {}", encoding="utf-8"
    )
    (tmp_path / "src/main/java/com/example/repository/OrderRepository.java").write_text(
        "@Repository interface OrderRepository extends JpaRepository<Order, Long> {}",
        encoding="utf-8",
    )
    (tmp_path / "src/test/java/com/example/OrderServiceTest.java").write_text(
        "class OrderServiceTest {}", encoding="utf-8"
    )

    metadata = scan_repository(tmp_path, "analysis-1")

    assert metadata["framework"] == "Spring Boot"
    assert "Maven" in metadata["build_tools"]
    assert len(metadata["controllers"]) == 1
    assert len(metadata["services"]) == 1
    assert len(metadata["repositories"]) == 1
    assert len(metadata["test_files"]) == 1
    assert metadata["controllers"][0]["evidence"] != "package com.example.controller;"
    assert metadata["api_inventory"][0]["path"] == "/orders/{id}"


def test_repo_scanner_detects_cloud_provider_evidence(tmp_path: Path) -> None:
    (tmp_path / ".github/workflows").mkdir(parents=True)
    (tmp_path / "src/main/resources").mkdir(parents=True)

    (tmp_path / "pom.xml").write_text(
        """
<project>
  <dependencies>
    <dependency>
      <groupId>com.amazonaws</groupId>
      <artifactId>aws-java-sdk-s3</artifactId>
      <version>1.11.534</version>
    </dependency>
    <dependency>
      <groupId>com.azure</groupId>
      <artifactId>azure-storage-blob</artifactId>
      <version>12.25.0</version>
    </dependency>
    <dependency>
      <groupId>com.google.cloud</groupId>
      <artifactId>google-cloud-storage</artifactId>
      <version>2.40.1</version>
    </dependency>
  </dependencies>
</project>
""",
        encoding="utf-8",
    )
    fake_access_key = "AKIA" + "1234567890ABCDEF"
    (tmp_path / "Dockerfile").write_text(
        f"FROM eclipse-temurin:17\nENV AWS_ACCESS_KEY_ID={fake_access_key}\n",
        encoding="utf-8",
    )
    (tmp_path / "src/main/resources/application.yml").write_text(
        """
archive:
  azure: https://demo.blob.core.windows.net/claims
  gcp: gs://claims-archive
""",
        encoding="utf-8",
    )

    metadata = scan_repository(tmp_path, "analysis-cloud")

    assert metadata["detected_cloud_providers"] == ["AWS", "Azure", "GCP"]
    services = {
        (item["provider"], item["service"])
        for item in metadata["detected_cloud_services"]
    }
    assert ("AWS", "S3") in services
    assert ("AWS", "credential environment") in services
    assert ("Azure", "Blob Storage") in services
    assert ("GCP", "Cloud Storage") in services
